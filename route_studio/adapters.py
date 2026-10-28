"""Device adapters. No shell execution and no implicit selection of devices."""
from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
import time


class DeviceError(RuntimeError):
    pass


_adb_cache_lock = threading.Lock()


def command(args, timeout=15):
    try:
        result = subprocess.run([str(a) for a in args], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except FileNotFoundError:
        raise DeviceError(f"未找到程序：{args[0]}") from None
    except subprocess.TimeoutExpired:
        raise DeviceError(f"设备命令超时（{timeout} 秒），请检查连接") from None
    output = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode:
        raise DeviceError(output[-1800:] or f"命令失败，退出码 {result.returncode}")
    return output


def adb_path():
    # Prefer the packaged tools; no system SDK or PATH configuration is needed.
    if getattr(sys, "frozen", False):
        bundled = Path(sys._MEIPASS) / "platform-tools" / "adb.exe"
        if bundled.is_file():
            # ADB leaves a background server running. Run it from user data so
            # that upgrading/uninstalling the app does not lock installed files.
            fingerprint = hashlib.sha256()
            for name in ('adb.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll'):
                component = bundled.parent / name
                if not component.is_file():
                    raise DeviceError('内置 ADB 组件不完整，请重新安装 Windows 版')
                fingerprint.update(component.read_bytes())
            cache = Path(os.environ['LOCALAPPDATA']) / 'CampusRouteStudio' / 'platform-tools' / fingerprint.hexdigest()[:16]
            with _adb_cache_lock:
                if not (cache / '.ready').is_file():
                    shutil.copytree(bundled.parent, cache, dirs_exist_ok=True)
                    (cache / '.ready').write_text('ready', encoding='ascii')
            return str(cache / 'adb.exe')
    found = shutil.which("adb")
    if found:
        return found
    roots = [os.environ.get("ANDROID_HOME", ""), os.environ.get("ANDROID_SDK_ROOT", ""),
             str(Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk")]
    for root in roots:
        path = Path(root) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
        if root and path.is_file():
            return str(path)
    raise DeviceError("ADB 文件缺失，请重新安装完整 Windows 安装包。源码开发需要 Android Platform-Tools。")


def serial_value(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:\-]{1,160}", value):
        raise ValueError("请选择有效设备序列号")
    return value


def list_android_devices():
    output = command([adb_path(), "devices", "-l"])
    devices = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[1] not in ("device", "offline", "unauthorized", "recovery", "sideload"):
            continue
        model = next((p.split(":", 1)[1].replace("_", " ") for p in parts[2:] if p.startswith("model:")), parts[0])
        devices.append({"serial": parts[0], "state": parts[1], "model": model})
    return devices


def connect_android(address):
    # This UI is for a local MuMu instance, not a general remote shell service.
    if not isinstance(address, str) or not re.fullmatch(r"(?:127\.0\.0\.1|localhost):[0-9]{1,5}", address):
        raise ValueError("请输入本机 MuMu ADB 地址，例如 127.0.0.1:16384（端口以 MuMu 设置为准）")
    port = int(address.rsplit(":", 1)[1])
    if not 1 <= port <= 65535:
        raise ValueError("端口无效")
    output = command([adb_path(), "connect", address])
    if "connected to" not in output.lower():
        raise DeviceError(output)
    return {"message": output}


class PreviewAdapter:
    def open(self):
        pass

    def send(self, point):
        pass

    def close(self):
        pass


from .android_direct import AndroidDirectAdapter as AndroidAdapter


def probe_android_direct(serial):
    return AndroidAdapter(serial).probe()


class MuMuAdapter:
    """Official CLI provides coordinates. It has no documented reset-to-real-GPS command."""
    def __init__(self, manager, instance):
        path = Path(manager or "")
        if not path.is_file() or path.name.lower() != "mumumanager.exe":
            raise ValueError("请选择现有 MuMuManager.exe（MuMu 4.0.0.3179 及以上）")
        if not str(instance).isdigit() or not 0 <= int(instance) <= 999:
            raise ValueError("MuMu 实例编号应为 0–999")
        self.manager, self.instance = str(path.resolve()), str(int(instance))
        self.used = False

    def open(self):
        output = command([self.manager, "info", "-v", self.instance])
        try:
            info = json.loads(output)
        except ValueError:
            raise DeviceError("MuMu 没有返回可识别的实例信息，请检查版本。" + output[-800:]) from None
        if isinstance(info, dict) and self.instance in info:
            info = info[self.instance]
        if not isinstance(info, dict) or not info.get("is_android_started"):
            raise DeviceError("指定 MuMu 实例尚未启动 Android，请先在 MuMu 中打开它")

    def send(self, point):
        from .coordinates import wgs_to_mumu
        latitude, longitude = wgs_to_mumu(point['lat'], point['lon'])
        output = command([self.manager, "control", "-v", self.instance, "tool", "location",
                          "-lon", f'{longitude:.8f}', "-lat", f'{latitude:.8f}'])
        from .mumu import check_reply
        check_reply(output)
        self.used = True

    def close(self):
        if self.used:
            raise DeviceError("MuMu 直接定位已停止发送，但会保留最后位置；请在 MuMu 虚拟定位面板手动恢复。")


class EmulatorConsole:
    def __init__(self, serial):
        match = re.fullmatch(r"emulator-(\d+)", serial)
        if not match:
            raise ValueError("虚拟传感器模式仅支持 Android 官方 Emulator（emulator-端口）")
        self.sock = socket.create_connection(("127.0.0.1", int(match.group(1))), timeout=4)
        self.stream = self.sock.makefile("rwb", buffering=0)
        try:
            welcome = self.read()
            if "Authentication required" in welcome:
                token = (Path.home() / ".emulator_console_auth_token").read_text().strip()
                self.execute("auth " + token)
        except Exception:
            self.close()
            raise

    def read(self):
        lines = []
        for _ in range(200):
            line = self.stream.readline(8192).decode("utf-8", "replace").strip()
            if not line:
                raise DeviceError("Emulator 控制台连接已关闭")
            if line.startswith("KO"):
                raise DeviceError(line)
            if line == "OK":
                return "\n".join(lines)
            lines.append(line)
        raise DeviceError("Emulator 控制台响应无效")

    def execute(self, text):
        self.stream.write((text + "\n").encode("utf-8"))
        return self.read()

    def close(self):
        self.stream.close()
        self.sock.close()


class AVDAdapter:
    def __init__(self, serial, sensor=False):
        self.serial = serial_value(serial)
        self.sensor = bool(sensor)
        self.console = None
        self.sensor_thread = None
        self.sensor_stop = threading.Event()
        self.moving = False
        self.sensor_error = None
        self.original_acceleration = None
        self.location_sent = False

    def open(self):
        self.console = EmulatorConsole(self.serial)
        if self.sensor:
            original = self.console.execute("sensor get acceleration")
            match = re.search(r"=\s*([-+\d.eE]+):([-+\d.eE]+):([-+\d.eE]+)", original)
            if not match:
                raise DeviceError("该 AVD 未提供可读取的加速度传感器，请关闭传感器选项")
            self.original_acceleration = ":".join(match.groups())
            self.sensor_thread = threading.Thread(target=self._sensors, daemon=True)
            self.sensor_thread.start()

    def _sensors(self):
        console = None
        try:
            console = EmulatorConsole(self.serial)
            start = time.monotonic()
            while not self.sensor_stop.is_set():
                t = time.monotonic() - start
                # Deterministic test waveform; not a biomechanical model or a pedometer.
                if self.moving:
                    values = f"{0.5 * math.sin(2 * math.pi * 1.4 * t):.4f}:{0.8 * math.cos(2 * math.pi * 2.8 * t):.4f}:{9.80665 + 1.5 * math.sin(2 * math.pi * 2.8 * t):.4f}"
                else:
                    values = self.original_acceleration
                console.execute("sensor set acceleration " + values)
                self.sensor_stop.wait(0.05)
        except Exception as exc:
            self.sensor_error = str(exc)
        finally:
            if console:
                console.close()

    def send(self, point):
        if self.sensor_error:
            raise DeviceError("AVD 传感器连接失败：" + self.sensor_error)
        self.moving = point["speed"] > 0
        self.console.execute(f'geo fix {point["lon"]:.8f} {point["lat"]:.8f} 0 8 {point["speed"] * 1.94384449:.4f}')
        self.location_sent = True

    def close(self):
        errors = []
        self.sensor_stop.set()
        if self.sensor_thread:
            self.sensor_thread.join(timeout=6)
            if self.sensor_thread.is_alive():
                errors.append("传感器发送线程尚未退出，请关闭该测试模拟器")
        if self.console:
            try:
                if self.original_acceleration:
                    self.console.execute("sensor set acceleration " + self.original_acceleration)
            except Exception as exc:
                errors.append(str(exc))
            finally:
                self.console.close()
                self.console = None
        if self.location_sent:
            errors.append("AVD 会保留最后定位；请在 Emulator 的 Location 面板重新设置。")
        if errors:
            raise DeviceError("；".join(errors))


def make_adapter(config):
    mode = config.get("mode", "preview")
    if config.get("sensor") and mode != "avd":
        raise ValueError("只有 Android 官方 Emulator 模式支持此加速度测试选项")
    if mode == "preview":
        return PreviewAdapter()
    if mode == "android":
        return AndroidAdapter(config.get("serial"))
    if mode == "mumu":
        return MuMuAdapter(config.get("manager"), config.get("instance", 0))
    if mode == "avd":
        return AVDAdapter(config.get("serial"), config.get("sensor", False))
    if mode == "ios":
        from .ios_adapter import IOSAdapter
        return IOSAdapter(config.get("udid", ""))
    raise ValueError("未知输出模式")

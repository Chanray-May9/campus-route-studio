"""ADB app_process transport. Copies a temporary DEX JAR, never installs an APK."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import uuid


class AndroidDirectAdapter:
    def __init__(self, serial):
        from . import adapters
        self.api = adapters
        self.serial = adapters.serial_value(serial)
        self.adb = adapters.adb_path()
        self.process = self.reader = None
        self.remote = None
        self.packets = queue.Queue(maxsize=64)
        self.sequence = 0
        self.closed_packet = None
        self.logs = []
        self.started = False

    def _adb(self, *args, timeout=15):
        return self.api.command([self.adb, '-s', self.serial, *args], timeout=timeout)

    def _artifact(self):
        base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
        candidates = [base / 'campus-route-direct.jar', base / 'build/campus-route-direct.jar']
        found = next((path for path in candidates if path.is_file()), None)
        if found is None:
            raise self.api.DeviceError('缺少安卓直连组件，请重新安装完整 Windows 版。源码构建请运行 scripts/build_android_bridge.py。')
        return found

    def _original_mode(self):
        output = self._adb('shell', 'appops', 'get', '--user', 'current', 'com.android.shell', 'android:mock_location')
        # Only restore the package mode. UID overrides are left untouched.
        modes = re.findall(r'^\s*MOCK_LOCATION:\s*(allow|ignore|deny|default|foreground)\b', output, re.M)
        if len(modes) == 1:
            return {'allow': 0, 'ignore': 1, 'deny': 2, 'default': 3, 'foreground': 4}[modes[0]]
        if not modes and ('No operations' in output or re.search(r'^Uid mode:', output, re.M)):
            return 3
        raise self.api.DeviceError('无法确定安卓原有模拟位置权限，未修改权限：' + output[-500:])

    def _read(self):
        try:
            for line in self.process.stdout:
                if not line.startswith('CRS1 '):
                    self.logs = (self.logs + [line.strip()[-500:]])[-8:]
                    continue
                packet = json.loads(line[5:])
                if not isinstance(packet, dict) or not isinstance(packet.get('id'), int):
                    raise ValueError('Invalid direct protocol response')
                if packet.get('closed'):
                    self.closed_packet = packet
                self.packets.put(packet, timeout=1)
        except Exception as error:
            self.logs = (self.logs + [str(error)])[-8:]
        finally:
            try:
                self.packets.put(None, timeout=1)
            except queue.Full:
                pass

    def _receive(self, sequence, timeout):
        try:
            packet = self.packets.get(timeout=timeout)
        except queue.Empty:
            raise self.api.DeviceError('安卓直连响应超时；该系统可能限制 ADB 定位进程。' + '\n'.join(self.logs)[-700:]) from None
        if packet is None:
            raise self.api.DeviceError('安卓直连进程已退出：' + '\n'.join(self.logs)[-700:])
        if packet['id'] != sequence:
            raise self.api.DeviceError('安卓直连响应序号错误，已停止本次连接')
        if not packet.get('ok'):
            detail = packet.get('error', '未知系统限制')
            if packet.get('cleanupError'):
                detail += '；清理未完成：' + packet['cleanupError']
            raise self.api.DeviceError('安卓直连失败：' + detail)
        return packet

    def _launch(self, argument):
        jar = self._artifact()
        if self._adb('get-state').strip() != 'device':
            raise self.api.DeviceError('安卓设备离线或尚未授权 USB 调试')
        try:
            sdk = int(self._adb('shell', 'getprop', 'ro.build.version.sdk').strip())
        except ValueError:
            raise self.api.DeviceError('无法读取安卓系统版本') from None
        if sdk < 26:
            raise self.api.DeviceError('安卓直连要求 Android 8 或更高版本；不会自动安装手机软件')
        self.remote = '/data/local/tmp/campus-route-' + uuid.uuid4().hex + '.jar'
        self._adb('push', str(jar), self.remote, timeout=30)
        self._adb('shell', 'chmod', '444', self.remote)
        self.process = subprocess.Popen(
            [self.adb, '-s', self.serial, 'shell', '-T', 'app_process',
             '-Djava.class.path=' + self.remote, '/data/local/tmp', 'org.campusroute.bridge.Main', str(argument)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        return self._receive(0, 10)

    def _request(self, action, point=None):
        if self.process is None or self.process.poll() is not None:
            raise self.api.DeviceError('安卓直连进程未运行，请重新连接')
        self.sequence += 1
        packet = {'id': self.sequence, 'action': action}
        if point is not None:
            packet['point'] = point
        try:
            self.process.stdin.write(json.dumps(packet, allow_nan=False, separators=(',', ':')) + '\n')
            self.process.stdin.flush()
        except (OSError, ValueError):
            raise self.api.DeviceError('无法向安卓发送直连命令，请检查 USB 连接') from None
        return self._receive(self.sequence, 5)

    def open(self):
        try:
            mode = self._original_mode()
            ready = self._launch(mode)
            if not ready.get('ready') or 'gps' not in ready.get('providers', []):
                raise self.api.DeviceError('安卓没有确认 GPS 直连通道就绪')
            self.started = True
        except Exception as error:
            try:
                self.close()
            except Exception as cleanup:
                raise self.api.DeviceError(str(error) + '；清理未确认：' + str(cleanup)) from error
            raise

    def probe(self):
        try:
            result = self._launch('probe')
            if not result.get('probe'):
                raise self.api.DeviceError('安卓没有返回有效直连检测结果')
            result['message'] = '安卓直连基础检测通过，手机不安装 APK。开始时仍会验证定位权限与实际通道。'
            if result.get('locationEnabled') is False:
                result['message'] += '请先打开手机系统定位。'
            return result
        finally:
            self.close()

    def send(self, point):
        clean = {}
        for name, low, high, default in [('lat', -90, 90, None), ('lon', -180, 180, None),
                                        ('speed', 0, 150, 0), ('bearing', 0, 360, 0), ('accuracy', .1, 10000, 5)]:
            raw = point.get(name, default)
            if isinstance(raw, bool):
                raise ValueError('安卓定位参数无效：' + name)
            try:
                value = float(raw)
            except (ValueError, TypeError):
                raise ValueError('安卓定位参数无效：' + name) from None
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError('安卓定位参数超出范围：' + name)
            clean[name] = value
        self._request('update', clean)

    def close(self):
        failures = []
        process = self.process
        if process is not None:
            if self.started and process.poll() is None:
                try:
                    self._request('stop')
                except Exception as error:
                    failures.append(str(error))
            try:
                process.stdin.close()
            except (OSError, ValueError):
                pass  # The remote process may have closed the pipe already.
            try:
                process.wait(timeout=12)
                if process.returncode:
                    failures.append('安卓直连退出码 ' + str(process.returncode))
            except (OSError, subprocess.TimeoutExpired) as error:
                failures.append('未确认安卓退出：' + str(error))
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            if self.reader is not None:
                self.reader.join(timeout=2)
            process.stdout.close()
            if self.closed_packet and self.closed_packet.get('cleanupError'):
                failures.append(self.closed_packet['cleanupError'])
            self.process = self.reader = None
        if self.remote is not None:
            try:
                self._adb('shell', 'rm', '-f', self.remote, timeout=5)
            except Exception as error:
                failures.append('临时文件清理未确认：' + str(error))
            self.remote = None
        self.started = False
        if failures:
            raise self.api.DeviceError('；'.join(failures))

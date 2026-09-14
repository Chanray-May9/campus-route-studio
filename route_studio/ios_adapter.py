"""USB iOS developer location playback; tested against pymobiledevice3 10.7.4.

Only latitude/longitude are injected. This interface cannot inject Core Motion,
speed, or bearing. Pairing, Developer Mode, and DDI mounting are prerequisites;
this module never enables them or starts an elevated tunnel daemon.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import math
import re
import struct
import threading
from types import SimpleNamespace
from typing import Any


class IOSAdapterError(RuntimeError):
    """A recoverable iOS setup, transport, or restoration error."""


def _dependencies() -> SimpleNamespace:
    try:
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
        from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
        from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
        from pymobiledevice3.usbmux import list_devices
    except ImportError as exc:
        raise IOSAdapterError(
            "iOS 依赖缺失或版本不兼容。请安装 pymobiledevice3==10.7.4。"
        ) from exc
    return SimpleNamespace(
        lockdown=create_using_usbmux, tunnel=UserspaceRsdTunnel,
        rsd=RemoteServiceDiscoveryService, dvt=DvtProvider,
        location=LocationSimulation, list_devices=list_devices,
    )


def _same_device(left: str, right: str) -> bool:
    return left.replace("-", "").lower() == right.replace("-", "").lower()


def _explain(exc: BaseException) -> str:
    kind = type(exc).__name__
    if isinstance(exc, (TimeoutError, concurrent.futures.TimeoutError)):
        return "iOS 操作超时；请检查数据线、手机解锁状态和开发者服务。"
    if kind in {"NotPairedError", "PairingDialogResponsePendingError", "UserDeniedPairingError"}:
        return "iPhone 尚未信任此电脑；请先手动完成信任和配对。"
    if kind in {"PasswordRequiredError", "DeviceLockedError"}:
        return "请解锁 iPhone 后重试。"
    if kind in {"NoDeviceConnectedError", "DeviceNotFoundError", "ConnectionFailedToUsbmuxdError"}:
        return "未连接所选 iPhone；请检查 USB 和 Windows Apple Mobile Device Service。"
    if kind in {"InvalidServiceError", "DeveloperModeIsNotEnabledError"}:
        return "iOS 开发者服务不可用；请手动开启开发者模式（iOS 16+）并挂载 DDI。"
    return str(exc) or kind


class _EventLoop:
    """Keep tunnel tasks alive between synchronous calls from the playback worker."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="ios-location-loop")
        self.thread.start()
        if not self.ready.wait(5):
            raise IOSAdapterError("iOS 后台事件循环启动超时。")

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.ready.set()
        self.loop.run_forever()
        pending = asyncio.all_tasks(self.loop)
        for task in pending:
            task.cancel()
        if pending:
            async def drain() -> None:
                await asyncio.wait(pending, timeout=1)
            self.loop.run_until_complete(drain())
        self.loop.close()

    def call(self, coro: Any, timeout: float) -> Any:
        async def bounded() -> Any:
            return await asyncio.wait_for(coro, timeout=timeout)
        future = asyncio.run_coroutine_threadsafe(bounded(), self.loop)
        try:
            return future.result(timeout=timeout + 2)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise TimeoutError("iOS operation timed out") from None

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=3)


async def _local_tunnels() -> dict[str, Any]:
    """Read only the local tunneld registry, with bounds enforced by the caller."""
    reader, writer = await asyncio.open_connection("127.0.0.1", 49151)
    try:
        writer.write(b"GET / HTTP/1.1\r\nHost: 127.0.0.1:49151\r\nConnection: close\r\n\r\n")
        await writer.drain()
        header = await reader.readuntil(b"\r\n\r\n")
        if header.split(b"\r\n", 1)[0].split()[1:2] != [b"200"]:
            raise IOSAdapterError("本地 tunneld 未返回有效设备列表。")
        # FastAPI's JSON response has a Content-Length; reject unbounded/chunked data.
        length = re.search(br"(?im)^content-length:\s*(\d+)\s*$", header)
        if length is None or int(length[1]) > 1024 * 1024:
            raise IOSAdapterError("本地 tunneld 响应格式异常。")
        payload = json.loads(await reader.readexactly(int(length[1])))
        if not isinstance(payload, dict):
            raise IOSAdapterError("本地 tunneld 设备列表格式异常。")
        return payload
    finally:
        writer.close()
        await writer.wait_closed()


class _LegacyLocation:
    """Pre-17 Apple developer protocol, closing each short-lived service explicitly."""

    def __init__(self, lockdown: Any) -> None:
        self.lockdown = lockdown

    async def _command(self, data: bytes) -> None:
        service = await self.lockdown.start_lockdown_developer_service("com.apple.dt.simulatelocation")
        try:
            await service.sendall(data)
        finally:
            await service.close()

    async def set(self, latitude: float, longitude: float) -> None:
        lat, lon = str(latitude).encode("ascii"), str(longitude).encode("ascii")
        await self._command(struct.pack(">I", 0) + struct.pack(">I", len(lat)) + lat
                            + struct.pack(">I", len(lon)) + lon)

    async def clear(self) -> None:
        await self._command(struct.pack(">I", 1))


class IOSAdapter:
    """Single selected USB iPhone; synchronous open/send/close from one worker.

    iOS 17.4+ uses one persistent userspace tunnel. iOS 17.0–17.3.1 requires an
    already-running local tunneld. Pre-17 uses a persistent lockdown connection.
    Restoration is attempted on errors and close; transport loss can prevent it,
    in which case close raises instead of claiming the real GPS was restored.
    """

    def __init__(self, udid: str, *, timeout: float = 8.0, open_timeout: float = 30.0) -> None:
        if not isinstance(udid, str) or not udid.strip():
            raise ValueError("请选择明确的 iPhone UDID。")
        if not math.isfinite(timeout) or not math.isfinite(open_timeout) or min(timeout, open_timeout) <= 0:
            raise ValueError("超时时间必须为有限正数。")
        self.udid = udid.strip()
        self.timeout = timeout
        self.open_timeout = open_timeout
        self._runner: _EventLoop | None = None
        self._resources: list[Any] = []
        self._location: Any = None
        self._needs_clear = False
        self._opened = False

    async def _open(self) -> None:
        dep = _dependencies()
        lockdown = await dep.lockdown(serial=self.udid, autopair=False, connection_type="USB")
        self._resources.append(lockdown.close)
        if not _same_device(str(lockdown.udid), self.udid):
            raise IOSAdapterError("连接设备与所选 UDID 不匹配，已停止。")
        if not lockdown.paired:
            raise IOSAdapterError("iPhone 尚未信任此电脑；请先手动完成信任和配对。")
        numbers = re.findall(r"\d+", str(lockdown.product_version))
        if not numbers:
            raise IOSAdapterError("无法识别所选 iPhone 的 iOS 版本。")
        version = tuple(int(n) for n in (numbers + ["0", "0"])[:3])
        if version < (17, 0, 0):
            self._location = _LegacyLocation(lockdown)
            return
        if version >= (17, 4, 0):
            tunnel = dep.tunnel(serial=self.udid, autopair=False, remotepairing_fallback=False)
            self._resources.append(tunnel.aclose)
            rsd = await tunnel.aopen()
        else:
            try:
                tunnels = await asyncio.wait_for(_local_tunnels(), timeout=self.timeout)
            except Exception as exc:
                raise IOSAdapterError(
                    "Windows 上 iOS 17.0–17.3.1 需要预先在管理员终端运行 "
                    "python -m pymobiledevice3 remote tunneld，并安装所需驱动。"
                ) from exc
            choices = next((v for k, v in tunnels.items() if _same_device(k, self.udid)), [])
            if not choices:
                raise IOSAdapterError("本地 tunneld 中没有所选 UDID；请检查该 iPhone 的隧道。")
            details = choices[0]
            rsd = dep.rsd((details["tunnel-address"], int(details["tunnel-port"])), name=details.get("interface"))
            self._resources.append(rsd.close)
            await rsd.connect()
        if not _same_device(str(rsd.udid), self.udid):
            raise IOSAdapterError("隧道设备与所选 UDID 不匹配，已停止。")
        dvt = dep.dvt(rsd)
        self._resources.append(dvt.close)
        await dvt.connect()
        self._location = dep.location(dvt)
        self._resources.append(self._location.close)
        await self._location.__aenter__()

    def open(self) -> None:
        if self._opened:
            return
        if self._runner is not None:
            raise IOSAdapterError("iOS 连接正在关闭。")
        self._runner = _EventLoop()
        try:
            self._runner.call(self._open(), self.open_timeout)
            self._opened = True
        except BaseException as exc:
            try:
                self.close()
            except IOSAdapterError as cleanup:
                raise IOSAdapterError(f"{_explain(exc)}；{cleanup}") from exc
            raise IOSAdapterError(_explain(exc)) from exc

    async def _send(self, latitude: float, longitude: float) -> None:
        # Even a timed-out write may have reached the phone, so always try clear.
        self._needs_clear = True
        await self._location.set(latitude, longitude)

    def send(self, point: dict[str, Any]) -> None:
        if not self._opened or self._runner is None:
            raise IOSAdapterError("请先打开 iOS 连接。")
        latitude, longitude = float(point["lat"]), float(point["lon"])
        if not math.isfinite(latitude) or not -90 <= latitude <= 90:
            raise ValueError("纬度必须位于 -90 到 90。")
        if not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise ValueError("经度必须位于 -180 到 180。")
        try:
            self._runner.call(self._send(latitude, longitude), self.timeout)
        except BaseException as exc:
            try:
                self.close()
            except IOSAdapterError as cleanup:
                raise IOSAdapterError(f"位置发送失败：{_explain(exc)}；{cleanup}") from exc
            raise IOSAdapterError(f"位置发送失败：{_explain(exc)}") from exc

    async def _cleanup(self) -> list[str]:
        errors = []
        if self._location is not None and self._needs_clear:
            try:
                await asyncio.wait_for(self._location.clear(), timeout=self.timeout)
            except BaseException as exc:
                errors.append("无法确认恢复真实定位；请重新连接所选 iPhone 并执行清除模拟定位：" + _explain(exc))
            finally:
                self._needs_clear = False
        self._location = None
        while self._resources:
            close = self._resources.pop()
            try:
                await asyncio.wait_for(close(), timeout=self.timeout)
            except BaseException as exc:
                errors.append("关闭 iOS 连接失败：" + _explain(exc))
        return errors

    def close(self) -> None:
        runner = self._runner
        if runner is None:
            return
        self._opened = False
        try:
            budget = self.timeout * (len(self._resources) + 1) + 1
            errors = runner.call(self._cleanup(), budget)
            if errors:
                raise IOSAdapterError("；".join(errors))
        except (TimeoutError, concurrent.futures.TimeoutError) as exc:
            raise IOSAdapterError("iOS 清理超时，无法确认恢复真实定位；请重新连接并清除模拟定位。") from exc
        finally:
            runner.stop()
            self._runner = None


def list_ios_devices(*, timeout: float = 8.0) -> list[dict[str, str]]:
    """Discover USB iPhones without initiating new trust/pairing or developer services."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("超时时间必须为有限正数。")

    async def discover() -> list[dict[str, str]]:
        dep = _dependencies()
        result = []
        seen = set()
        for device in await dep.list_devices():
            if not device.is_usb or device.serial in seen:
                continue
            seen.add(device.serial)
            lockdown = await dep.lockdown(serial=device.serial, autopair=False, connection_type="USB")
            try:
                result.append({"udid": device.serial, "name": str(lockdown.display_name),
                               "version": str(lockdown.product_version)})
            finally:
                await lockdown.close()
        return result

    runner = _EventLoop()
    try:
        return runner.call(discover(), timeout)
    except Exception as exc:
        raise IOSAdapterError(_explain(exc)) from exc
    finally:
        runner.stop()

"""Transport fakes: no iPhone, trust change, DDI mount, or location mutation."""

import asyncio
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from route_studio import ios_adapter as ios


class Fixture:
    def __init__(self, version="17.4"):
        self.calls = []
        self.lockdown = SimpleNamespace(
            udid="selected-phone", paired=True, product_version=version,
            display_name="Test iPhone", close=AsyncMock(side_effect=lambda: self.calls.append("lockdown.close")),
        )
        self.rsd = SimpleNamespace(
            udid="selected-phone", connect=AsyncMock(),
            close=AsyncMock(side_effect=lambda: self.calls.append("rsd.close")),
        )
        self.tunnel = SimpleNamespace(
            aopen=AsyncMock(return_value=self.rsd),
            aclose=AsyncMock(side_effect=lambda: self.calls.append("tunnel.close")),
        )
        self.dvt = SimpleNamespace(
            connect=AsyncMock(), close=AsyncMock(side_effect=lambda: self.calls.append("dvt.close")),
        )
        self.location = SimpleNamespace(
            __aenter__=AsyncMock(), set=AsyncMock(),
            clear=AsyncMock(side_effect=lambda: self.calls.append("clear")),
            close=AsyncMock(side_effect=lambda: self.calls.append("location.close")),
        )
        self.dep = SimpleNamespace(
            lockdown=AsyncMock(return_value=self.lockdown),
            tunnel=unittest.mock.Mock(return_value=self.tunnel),
            rsd=unittest.mock.Mock(return_value=self.rsd),
            dvt=unittest.mock.Mock(return_value=self.dvt),
            location=unittest.mock.Mock(return_value=self.location),
            list_devices=AsyncMock(return_value=[]),
        )


class IOSAdapterTests(unittest.TestCase):
    def adapter(self, fixture, **kwargs):
        dependency_patch = patch.object(ios, "_dependencies", return_value=fixture.dep)
        dependency_patch.start()
        self.addCleanup(dependency_patch.stop)
        adapter = ios.IOSAdapter("selected-phone", **kwargs)
        self.addCleanup(adapter.close)
        return adapter

    def test_modern_reuses_connection_and_clears_before_teardown(self):
        fixture = Fixture()
        adapter = self.adapter(fixture)
        adapter.open()
        adapter.send({"lat": 30, "lon": 120, "speed": 2, "bearing": 90})
        adapter.send({"lat": 30.1, "lon": 120.1})
        adapter.close()
        fixture.dep.lockdown.assert_awaited_once_with(
            serial="selected-phone", autopair=False, connection_type="USB")
        fixture.dep.tunnel.assert_called_once_with(
            serial="selected-phone", autopair=False, remotepairing_fallback=False)
        self.assertEqual(fixture.location.set.await_count, 2)
        self.assertEqual(fixture.calls, ["clear", "location.close", "dvt.close", "tunnel.close", "lockdown.close"])
        self.assertIsNone(adapter._runner)

    def test_send_failure_clears_same_location_and_closes(self):
        fixture = Fixture()
        fixture.location.set.side_effect = ConnectionError("cable disconnected")
        adapter = self.adapter(fixture)
        adapter.open()
        with self.assertRaisesRegex(ios.IOSAdapterError, "位置发送失败"):
            adapter.send({"lat": 30, "lon": 120})
        fixture.location.clear.assert_awaited_once()
        self.assertEqual(fixture.dep.location.call_count, 1)
        self.assertIsNone(adapter._runner)

    def test_send_timeout_attempts_clear(self):
        fixture = Fixture()
        async def stalled(*args):
            await asyncio.Event().wait()
        fixture.location.set.side_effect = stalled
        adapter = self.adapter(fixture, timeout=0.03)
        adapter.open()
        with self.assertRaisesRegex(ios.IOSAdapterError, "超时"):
            adapter.send({"lat": 30, "lon": 120})
        fixture.location.clear.assert_awaited_once()

    def test_clear_failure_is_reported_but_all_resources_close(self):
        fixture = Fixture()
        fixture.location.clear.side_effect = ConnectionError("lost USB")
        adapter = self.adapter(fixture)
        adapter.open()
        adapter.send({"lat": 30, "lon": 120})
        with self.assertRaisesRegex(ios.IOSAdapterError, "无法确认恢复真实定位"):
            adapter.close()
        self.assertEqual(fixture.calls, ["location.close", "dvt.close", "tunnel.close", "lockdown.close"])

    def test_refuses_unpaired_and_wrong_devices(self):
        for change in ({"paired": False}, {"udid": "other-phone"}):
            with self.subTest(change=change):
                fixture = Fixture()
                for key, value in change.items():
                    setattr(fixture.lockdown, key, value)
                adapter = self.adapter(fixture)
                with self.assertRaises(ios.IOSAdapterError):
                    adapter.open()
                fixture.dep.tunnel.assert_not_called()
                fixture.lockdown.close.assert_awaited_once()

    def test_early_17_requires_existing_tunnel_for_selected_udid(self):
        fixture = Fixture("17.3.1")
        adapter = self.adapter(fixture)
        tunnels = {"other-phone": [{"tunnel-address": "::2", "tunnel-port": 2}],
                   "selected-phone": [{"tunnel-address": "::1", "tunnel-port": 123, "interface": "test"}]}
        with patch.object(ios, "_local_tunnels", AsyncMock(return_value=tunnels)):
            adapter.open()
        fixture.dep.tunnel.assert_not_called()
        fixture.dep.rsd.assert_called_once_with(("::1", 123), name="test")
        adapter.close()

    def test_early_17_never_falls_back_to_another_device(self):
        fixture = Fixture("17.0")
        adapter = self.adapter(fixture)
        with patch.object(ios, "_local_tunnels", AsyncMock(return_value={"other": []})):
            with self.assertRaisesRegex(ios.IOSAdapterError, "没有所选 UDID"):
                adapter.open()
        fixture.dep.rsd.assert_not_called()

    def test_legacy_short_lived_services_always_close(self):
        fixture = Fixture("16.7.1")
        connection = SimpleNamespace(sendall=AsyncMock(), close=AsyncMock())
        fixture.lockdown.start_lockdown_developer_service = AsyncMock(return_value=connection)
        adapter = self.adapter(fixture)
        adapter.open()
        adapter.send({"lat": 30, "lon": -120})
        adapter.close()
        self.assertEqual(connection.close.await_count, 2)
        data = connection.sendall.await_args_list[0].args[0]
        self.assertEqual(data[:4], struct.pack(">I", 0))
        self.assertEqual(connection.sendall.await_args_list[-1].args[0], struct.pack(">I", 1))
        fixture.dep.tunnel.assert_not_called()

    def test_invalid_coordinates_are_never_sent(self):
        fixture = Fixture()
        adapter = self.adapter(fixture)
        adapter.open()
        for point in ({"lat": float("nan"), "lon": 0}, {"lat": 0, "lon": 181}):
            with self.assertRaises(ValueError):
                adapter.send(point)
        fixture.location.set.assert_not_awaited()
        adapter.close()
        fixture.location.clear.assert_not_awaited()

    def test_discovery_is_usb_only_and_does_not_pair(self):
        fixture = Fixture()
        fixture.dep.list_devices.return_value = [
            SimpleNamespace(is_usb=False, serial="wifi-phone"),
            SimpleNamespace(is_usb=True, serial="selected-phone"),
        ]
        with patch.object(ios, "_dependencies", return_value=fixture.dep):
            self.assertEqual(ios.list_ios_devices(), [
                {"udid": "selected-phone", "name": "Test iPhone", "version": "17.4"}])
        fixture.dep.lockdown.assert_awaited_once_with(
            serial="selected-phone", autopair=False, connection_type="USB")
        fixture.dep.tunnel.assert_not_called()


if __name__ == "__main__":
    unittest.main()

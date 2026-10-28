"""Real pipes/subprocesses with a protocol peer; no Android device."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from route_studio.adapters import AndroidAdapter, DeviceError, make_adapter


class AndroidDirectTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.jar=self.root/'test.jar';self.jar.write_bytes(b'fixture');self.record=self.root/'events.json'
        self.calls=[];self.launches=[];self.sdk='35';self.appops='No operations.';self.scenario='normal'
        real_popen=subprocess.Popen
        def command(args,timeout=15):
            self.calls.append(args)
            if args[3:]==['get-state']:return 'device'
            if args[3:]==['shell','getprop','ro.build.version.sdk']:return self.sdk
            if args[3:6]==['shell','appops','get']:return self.appops
            return ''
        def launch(args,**kwargs):
            self.launches.append(args)
            peer=Path(__file__).parent/'fixtures/android_direct_peer.py'
            return real_popen([sys.executable,'-u',str(peer),args[-1],self.scenario,str(self.record)],**kwargs)
        self.patches=[patch('route_studio.adapters.adb_path',return_value='adb'),
                      patch('route_studio.adapters.command',side_effect=command),
                      patch('route_studio.android_direct.subprocess.Popen',side_effect=launch),
                      patch('route_studio.android_direct.AndroidDirectAdapter._artifact',return_value=self.jar)]
        for p in self.patches:p.start()
        self.adapter=AndroidAdapter('selected-phone')

    def tearDown(self):
        try:self.adapter.close()
        except DeviceError:pass
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def events(self):return json.loads(self.record.read_text(encoding='utf-8'))

    def test_default_adapter_sends_and_stops_without_apk(self):
        self.assertIsInstance(make_adapter({'mode':'android','serial':'selected-phone'}),AndroidAdapter)
        self.adapter.open();self.adapter.send({'lat':30,'lon':120,'speed':2.8,'bearing':15});self.adapter.close()
        events=self.events();self.assertTrue(events[-1]['cleaned']);self.assertIn('stop',[e.get('action') for e in events])
        point=next(e['point'] for e in events if e.get('action')=='update')
        self.assertEqual(point,{'lat':30.,'lon':120.,'speed':2.8,'bearing':15.,'accuracy':5.})
        self.assertEqual(self.launches[0][-1],'3');self.assertIn('app_process',self.launches[0])
        self.assertTrue(all(c[1:3]==['-s','selected-phone'] for c in self.calls))
        self.assertFalse(any('install' in c or 'broadcast' in c for c in self.calls))
        self.assertTrue(any(c[3:6]==['shell','chmod','444'] for c in self.calls))
        self.assertTrue(any(c[3:6]==['shell','rm','-f'] for c in self.calls))

    def test_original_package_mode_is_preserved(self):
        self.appops='Uid mode: MOCK_LOCATION: allow\n  MOCK_LOCATION: ignore; time=+2s'
        self.adapter.open();self.adapter.close();self.assertEqual(self.launches[0][-1],'1')
        self.assertFalse(any('set' in c for c in self.calls))

    def test_unknown_permission_output_fails_before_push(self):
        self.appops='vendor unsupported output'
        with self.assertRaisesRegex(DeviceError,'未修改权限'):self.adapter.open()
        self.assertFalse(self.launches);self.assertFalse(any('push' in c for c in self.calls))

    def test_old_android_has_no_install_fallback(self):
        self.sdk='25'
        with self.assertRaisesRegex(DeviceError,'Android 8'):self.adapter.open()
        self.assertFalse(self.launches);self.assertFalse(any('push' in c or 'install' in c for c in self.calls))

    def test_probe_does_not_request_mock_operation(self):
        self.assertTrue(self.adapter.probe()['probe']);self.assertEqual(self.launches[0][-1],'probe')
        self.assertFalse(any('appops' in c for c in self.calls))

    def test_denied_start_cleans_temporary_file(self):
        self.scenario='denied'
        with self.assertRaisesRegex(DeviceError,'permission denied'):self.adapter.open()
        self.assertFalse(self.adapter.started);self.assertIsNone(self.adapter.process)
        self.assertTrue(any(c[3:6]==['shell','rm','-f'] for c in self.calls))

    def test_network_only_is_not_gps_readiness(self):
        self.scenario='no-gps'
        with self.assertRaisesRegex(DeviceError,'GPS'):self.adapter.open()
        self.assertTrue(self.events()[-1]['cleaned'])

    def test_invalid_coordinates_never_sent(self):
        self.adapter.open()
        for p in [{'lat':float('nan'),'lon':120},{'lat':True,'lon':120},{'lat':30,'lon':200}]:
            with self.assertRaises(ValueError):self.adapter.send(p)
        self.adapter.close();self.assertFalse(any(e.get('action')=='update' for e in self.events()))

    def test_sequence_mismatch_is_detected(self):
        self.scenario='bad-sequence';self.adapter.open()
        with self.assertRaisesRegex(DeviceError,'序号'):self.adapter.send({'lat':30,'lon':120})
        self.adapter.close();self.assertTrue(self.events()[-1]['cleaned'])

    def test_disconnect_and_exit_failure_are_reported(self):
        self.scenario='disconnect';self.adapter.open()
        with self.assertRaisesRegex(DeviceError,'退出'):self.adapter.send({'lat':30,'lon':120})
        with self.assertRaisesRegex(DeviceError,'退出码 3'):self.adapter.close()

    def test_timeout_is_not_success(self):
        with self.assertRaisesRegex(DeviceError,'超时'):self.adapter._receive(0,.01)


if __name__=='__main__':unittest.main()

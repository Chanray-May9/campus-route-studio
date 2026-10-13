import unittest
from pathlib import Path
from unittest.mock import patch
from route_studio.adapters import DeviceError, MuMuAdapter
from route_studio.mumu import check_reply, discover_mumu

class MuMuTests(unittest.TestCase):
    def test_zero_error_code_is_success(self):
        self.assertEqual(check_reply('{"error_code":0,"errmsg":""}')["error_code"],0)
    def test_nonzero_cli_error_is_failure(self):
        with self.assertRaisesRegex(DeviceError,'not running'):
            check_reply('{"errcode":503,"errmsg":"not running"}')
    def test_discovery_reports_running_and_stopped_without_launching(self):
        with patch('route_studio.mumu.manager_candidates',return_value=[Path('MuMuManager.exe')]),patch('route_studio.mumu.command',return_value='{"1":{"name":"one","is_android_started":true},"0":{"name":"zero","is_android_started":false}}') as cmd:
            result=discover_mumu()
        self.assertEqual([i['running'] for i in result['managers'][0]['instances']],[False,True])
        self.assertEqual(cmd.call_args.args[0][1:],['info','-v','all'])
    def test_discovery_failure_does_not_return_a_usable_manager(self):
        with patch('route_studio.mumu.manager_candidates',return_value=[Path('MuMuManager.exe')]),patch('route_studio.mumu.command',return_value='{"errcode":503,"errmsg":"not running"}'):
            result=discover_mumu()
        self.assertEqual(result['managers'],[])
        self.assertEqual(result['errors'],['not running'])
    def test_failed_location_command_never_marks_adapter_used(self):
        adapter=MuMuAdapter.__new__(MuMuAdapter);adapter.manager='MuMuManager.exe';adapter.instance='1';adapter.used=False
        with patch('route_studio.adapters.command',return_value='{"errcode":503,"errmsg":"not running"}'):
            with self.assertRaises(DeviceError):adapter.send({'lon':120,'lat':30})
        self.assertFalse(adapter.used)

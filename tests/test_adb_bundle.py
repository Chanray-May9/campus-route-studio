import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from route_studio.adapters import adb_path


@unittest.skipUnless(sys.platform == 'win32', 'Windows bundle')
class BundledADBTests(unittest.TestCase):
    def test_server_binary_lives_outside_install_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / 'installed/platform-tools'
            tools.mkdir(parents=True)
            for name in ('adb.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll'):
                (tools / name).write_bytes(('fixture-' + name).encode())
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', str(root / 'installed'), create=True), patch.dict(os.environ, {'LOCALAPPDATA': str(root / 'userdata')}):
                first = Path(adb_path())
                self.assertTrue(first.is_relative_to(root / 'userdata'))
                self.assertFalse(first.is_relative_to(root / 'installed'))
                self.assertEqual(first.read_bytes(), (tools / 'adb.exe').read_bytes())
                self.assertEqual(adb_path(), str(first))
                (tools / 'adb.exe').write_bytes(b'new-version')
                second = Path(adb_path())
                self.assertNotEqual(first, second)
                self.assertEqual(second.read_bytes(), b'new-version')
                self.assertTrue(first.is_file(), 'existing server cache must remain untouched')


if __name__ == '__main__':
    unittest.main()

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(sys.platform == 'win32', 'Windows file locking')
class WindowsLauncherTests(unittest.TestCase):
    def test_second_shortcut_click_returns_to_existing_instance(self):
        import msvcrt
        source = Path(__file__).resolve().parents[1] / 'scripts/windows_entry.py'
        spec = importlib.util.spec_from_file_location('windows_entry', source)
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'CampusRouteStudio'
            state.mkdir()
            (state / 'desktop-session.json').write_text(json.dumps({'url': 'http://127.0.0.1:18765/?token=local-test-session'}), 'utf-8')
            with (state / 'desktop.lock').open('w+b') as owner:
                owner.write(b'0'); owner.flush(); owner.seek(0)
                msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
                try:
                    with patch.dict('os.environ', {'LOCALAPPDATA': directory}), patch.object(sys, 'argv', ['CampusRouteStudio.exe']), patch.object(launcher.webbrowser, 'open') as browser:
                        launcher.main()
                        browser.assert_called_once_with('http://127.0.0.1:18765/?token=local-test-session')
                finally:
                    owner.seek(0); msvcrt.locking(owner.fileno(), msvcrt.LK_UNLCK, 1)


if __name__ == '__main__':
    unittest.main()

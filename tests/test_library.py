import tempfile
from pathlib import Path
import unittest
from route_studio.library import RouteLibrary


class LibraryTests(unittest.TestCase):
    def test_infinite_loop_setting_persists(self):
        saved = self.library.save({**self.data, 'route': {**self.data['route'], 'loops': 0}})
        self.assertEqual(RouteLibrary(self.path).load(saved['id'])['route']['loops'], 0)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'data' / 'routes.sqlite3'
        self.library = RouteLibrary(self.path)
        self.data = {'name': '学校操场', 'route': {'points': [{'lat': 30, 'lon': 120}, {'lat': 30.001, 'lon': 120}], 'speed': 2.5, 'loops': 3}, 'motion': {'mode': 'alternating', 'low': 2, 'high': 3, 'sway': 0.5}}

    def tearDown(self):
        self.temp.cleanup()

    def test_persists_named_route_and_motion_across_instances(self):
        saved = self.library.save(self.data)
        fresh = RouteLibrary(self.path)
        restored = fresh.load(saved['id'])
        self.assertEqual(restored['route']['points'], self.data['route']['points'])
        self.assertEqual(restored['route']['loops'], 3)
        self.assertEqual(restored['motion']['sway'], 0.5)
        self.assertEqual(restored['motion']['mode'], 'alternating')

    def test_multiple_save_update_and_delete(self):
        first = self.library.save(self.data)
        second = self.library.save({**self.data, 'name': '校园外圈'})
        self.assertEqual(len(self.library.list()), 2)
        self.library.save({**self.data, 'id': first['id'], 'name': '新名称'})
        self.assertEqual(self.library.load(first['id'])['name'], '新名称')
        self.assertEqual(len(self.library.list()), 2)
        self.library.delete(first['id'])
        self.assertEqual(self.library.list()[0]['id'], second['id'])
        with self.assertRaises(ValueError):
            self.library.load(first['id'])

    def test_invalid_save_does_not_replace_existing_record(self):
        saved = self.library.save(self.data)
        for changes in ({'name': ''}, {'motion': {'sway': 20}}, {'route': {'points': []}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.library.save({**self.data, 'id': saved['id'], **changes})
        self.assertEqual(self.library.load(saved['id'])['name'], '学校操场')

    def test_unknown_update_never_creates_record(self):
        with self.assertRaises(ValueError):
            self.library.save({**self.data, 'id': 'unknown'})
        self.assertEqual(self.library.list(), [])

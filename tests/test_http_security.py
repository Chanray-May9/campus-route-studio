import http.client
import json
import threading
import unittest
from route_studio.server import LocalServer


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = LocalServer()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.application.playback.shutdown()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, method, path, body=None, auth=True, origin=True):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Cookie'] = 'campus_route_session=' + self.server.token
        if origin:
            headers['Origin'] = self.server.origin
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        status, content = response.status, response.read()
        connection.close()
        return status, content

    def test_authentication_and_origin_required(self):
        self.assertEqual(self.request('GET', '/api/status', auth=False)[0], 403)
        self.assertEqual(self.request('GET', '/api/status')[0], 200)
        self.assertEqual(self.request('POST', '/api/control', '{}', origin=False)[0], 403)

    def test_file_traversal_and_invalid_json(self):
        self.assertEqual(self.request('GET', '/../README.md')[0], 404)
        self.assertEqual(self.request('POST', '/api/start', '{')[0], 400)

    def test_preview_and_local_only(self):
        with self.assertRaises(ValueError):
            LocalServer(('0.0.0.0', 0))
        config = {'mode': 'preview', 'route': {'points': [{'lat': 30, 'lon': 120}, {'lat': 30.001, 'lon': 120}]}}
        self.assertEqual(self.request('POST', '/api/start', json.dumps(config))[0], 200)
        self.assertEqual(self.request('POST', '/api/control', '{"action":"stop"}')[0], 200)


if __name__ == '__main__':
    unittest.main()

"""Exercise every HTTP operation against mock using real loopback requests."""
import io
import json
import re
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mock_server import Handler, API, OPERATIONS
from validate import read, validator

UUID = '00000001-0000-4000-8000-000000000001'


class MockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def call(self, path, method='GET', body=None, headers=None):
        request = Request(self.base + path, data=body, headers=headers or {}, method=method)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None, response.headers

    def operation_request(self, op):
        headers = {'Authorization': 'Bearer mock-' + ('worker' if op['role'] == 'worker' else 'admin') + '-token', 'Idempotency-Key': UUID, 'X-Worker-Lease': UUID, 'Cookie': 'ottv2_refresh=mock-refresh'}
        value = read(op['request_example']) if op.get('request_example') else None
        path_id = value.get('submission_id', value.get('game_id', UUID)) if isinstance(value, dict) else UUID
        route = '/api/v1' + re.sub(r'\{\w+\}', path_id, op['path'])
        query = {p['name']: ('main.py' if p['name'] == 'path' else UUID) for p in API['paths'][op['path']][op['method']]['parameters'] if p['in'] == 'query' and p.get('required')}
        if query:
            route += '?' + urlencode(query)
        body = None
        if value is not None:
            if op['multipart']:
                archive = io.BytesIO()
                with zipfile.ZipFile(archive, 'w') as z:
                    z.writestr('main.py', 'print("READY example", flush=True)')
                boundary = 'contract-test-boundary'
                body = (f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\npython\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="source.zip"\r\nContent-Type: application/zip\r\n\r\n'.encode() + archive.getvalue() + f'\r\n--{boundary}--\r\n'.encode())
                headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
            else:
                body = json.dumps(value).encode()
                headers['Content-Type'] = 'application/json'
        return route, body, headers

    def test_all_operations(self):
        for op in OPERATIONS:
            with self.subTest(operation=op['operationId']):
                route, body, headers = self.operation_request(op)
                status, data, returned_headers = self.call(route, op['method'].upper(), body, headers)
                self.assertEqual(status, op['status'], data)
                self.assertEqual(returned_headers['X-Contract-Mock'], 'stateless-fixtures')
                if op['response']:
                    validator(op['response']).validate(data)
                else:
                    self.assertIsNone(data)

    def test_authorization_and_validation(self):
        self.assertEqual(self.call('/api/v1/admin/teams')[0], 401)
        self.assertEqual(self.call('/api/v1/admin/teams', headers={'Authorization':'Bearer mock-member-token'})[0], 403)
        self.assertEqual(self.call('/api/v1/matches/not-a-uuid', headers={'Authorization':'Bearer mock-member-token'})[0], 422)
        self.assertEqual(self.call('/api/v1/standings')[0], 422)
        self.assertEqual(self.call('/api/v1/announcements?page=0')[0], 422)
        op = next(o for o in OPERATIONS if o['operationId'] == 'createScrimmage')
        route, body, headers = self.operation_request(op)
        headers.pop('Idempotency-Key')
        self.assertEqual(self.call(route, 'POST', body, headers)[0], 422)
        headers['Idempotency-Key'] = UUID
        self.assertEqual(self.call(route, 'POST', b'{"opponent_id":"wrong-name"}', headers)[0], 422)
        headers['X-Mock-Status'] = '409'
        status, error, _ = self.call(route, 'POST', body, headers)
        self.assertEqual(status, 409)
        validator('Error').validate(error)

    def test_callback_id_mismatch_and_json_error(self):
        op = next(o for o in OPERATIONS if o['operationId'] == 'gameCallback')
        route, body, headers = self.operation_request(op)
        route = '/api/v1/internal/games/' + UUID
        self.assertEqual(self.call(route, 'POST', body, headers)[0], 422)
        self.assertEqual(self.call(route, 'POST', b'{', headers)[0], 422)

    def test_replay_fixture(self):
        status, replay, _ = self.call('/fixtures/replay.json')
        self.assertEqual(status, 200)
        validator('Replay').validate(replay)

    def test_refresh_cookie_flow(self):
        status, _, headers = self.call('/api/v1/auth/login', 'POST', b'{"email":"captain@example.test","password":"example"}', {'Content-Type':'application/json'})
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.call('/api/v1/auth/refresh', 'POST', headers={'Cookie':cookie})[0], 200)
        self.assertEqual(self.call('/api/v1/auth/refresh', 'POST')[0], 401)


if __name__ == '__main__':
    unittest.main(verbosity=2)

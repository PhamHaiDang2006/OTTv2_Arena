"""Stateless contract mock, not a backend. Bind to loopback only.
python contracts/mock_server.py --port 4010
"""
from __future__ import annotations

import argparse
import json
import re
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from validate import ROOT, read, validator, semantic_errors

OPERATIONS = read('operations.json')
API = read('openapi.yaml')
TOKENS = {'mock-member-token': 'member', 'mock-captain-token': 'captain', 'mock-admin-token': 'admin', 'mock-worker-token': 'worker'}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, data=None, headers=None):
        body = b'' if data is None else json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Contract-Mock', 'stateless-fixtures')
        origin = self.headers.get('Origin', '')
        parsed = urlsplit(origin)
        if parsed.hostname in ('localhost', '127.0.0.1'):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Credentials', 'true')
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def error(self, status, code, message):
        self.respond(status, {'error': {'code': code, 'message': message, 'details': {}}, 'request_id': '00000009-0000-4000-8000-000000000001'})

    def do_OPTIONS(self):
        self.respond(204, headers={'Access-Control-Allow-Methods': 'GET,POST,PUT,PATCH,OPTIONS', 'Access-Control-Allow-Headers': 'Authorization,Content-Type,Idempotency-Key,X-Worker-Lease,X-Mock-Status'})

    def handle_request(self):
        url = urlsplit(self.path)
        if url.path == '/fixtures/replay.json' and self.command == 'GET':
            return self.respond(200, read('examples/replay.json'))
        if url.path == '/openapi.json' and self.command == 'GET':
            return self.respond(200, API)
        for operation in OPERATIONS:
            pattern = '^/api/v1' + re.sub(r'\{\w+\}', r'([^/]+)', operation['path']) + '$'
            match = re.match(pattern, url.path)
            if operation['method'].upper() == self.command and match:
                return self.execute(operation, match.groups(), parse_qs(url.query))
        self.error(404, 'NOT_FOUND', 'No contract operation for this path/method')

    def execute(self, operation, path_values, query):
        # Consume bounded POST data before early rejection to avoid TCP resets.
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.error(400, 'INVALID_REQUEST', 'Invalid Content-Length')
        if length < 0 or length > 2 * 1024 * 1024:
            return self.error(413, 'PAYLOAD_TOO_LARGE', 'Request too large')
        raw = self.rfile.read(length)
        spec = API['paths'][operation['path']][operation['method']]
        role = TOKENS.get(self.headers.get('Authorization', '').removeprefix('Bearer '))
        required = operation['role']
        if required == 'refresh':
            if 'ottv2_refresh=mock-refresh' not in self.headers.get('Cookie', ''):
                return self.error(401, 'UNAUTHORIZED', 'Mock refresh cookie required; login first')
        elif required != 'public':
            if not role:
                return self.error(401, 'UNAUTHORIZED', 'Use a documented mock token')
            allowed = {'member': {'member', 'captain', 'admin'}, 'captain': {'captain', 'admin'}, 'admin': {'admin'}, 'worker': {'worker'}}[required]
            if role not in allowed:
                return self.error(403, 'FORBIDDEN', 'Role cannot call this operation')
        path_iter = iter(path_values)
        for p in spec['parameters']:
            value = next(path_iter) if p['in'] == 'path' else self.headers.get(p['name']) if p['in'] == 'header' else query.get(p['name'], [None])[0]
            if value is None:
                if p.get('required'):
                    return self.error(422, 'INVALID_REQUEST', f'Missing {p["name"]}')
                continue
            schema = p['schema']
            if schema.get('type') == 'integer':
                try:
                    value = int(value)
                except ValueError:
                    return self.error(422, 'INVALID_REQUEST', f'{p["name"]} must be integer')
            from jsonschema import Draft202012Validator, FormatChecker
            bundled = {'$defs': read('schemas/common.schema.json')['$defs'], **json.loads(json.dumps(schema).replace('#/components/schemas/', '#/$defs/'))}
            if list(Draft202012Validator(bundled, format_checker=FormatChecker()).iter_errors(value)):
                return self.error(422, 'INVALID_REQUEST', f'Invalid {p["name"]}')
        if operation['request']:
            try:
                if operation['multipart']:
                    content_type = self.headers.get('Content-Type', '')
                    message = BytesParser(policy=default).parsebytes(('Content-Type: ' + content_type + '\r\n\r\n').encode() + raw)
                    if not message.is_multipart():
                        raise ValueError('Expected multipart/form-data')
                    body = {}
                    for part in message.iter_parts():
                        name = part.get_param('name', header='content-disposition')
                        payload = part.get_payload(decode=True)
                        if name in body or name not in ('file', 'language'):
                            raise ValueError('Unexpected or repeated multipart field')
                        if name == 'file':
                            if len(payload) > 1048576 or not payload.startswith(b'PK'):
                                raise ValueError('Expected ZIP <= 1 MiB')
                            body[name] = part.get_filename() or 'source.zip'
                        else:
                            body[name] = payload.decode('utf-8')
                else:
                    if not self.headers.get('Content-Type', '').startswith('application/json'):
                        raise ValueError('Expected application/json')
                    body = json.loads(raw)
                failures = list(validator(operation['request']).iter_errors(body))
                if failures:
                    raise ValueError(failures[0].message)
                semantics = semantic_errors(operation['request'], body)
                if semantics:
                    raise ValueError(semantics[0])
                if operation['operationId'] in ('buildCallback', 'gameCallback'):
                    resource = 'submission_id' if operation['operationId'] == 'buildCallback' else 'game_id'
                    if body[resource] != path_values[0]:
                        raise ValueError('URL ID differs from callback ID')
            except (ValueError, UnicodeError, TypeError) as exc:
                return self.error(422, 'INVALID_REQUEST', str(exc))
        forced = self.headers.get('X-Mock-Status')
        if forced:
            if forced not in spec['responses'] or not forced.isdigit() or int(forced) < 400:
                return self.error(400, 'INVALID_MOCK_STATUS', 'Choose a documented error HTTP status')
            return self.error(int(forced), {401:'UNAUTHORIZED',403:'FORBIDDEN',404:'NOT_FOUND',409:'STATE_CONFLICT',413:'PAYLOAD_TOO_LARGE',422:'INVALID_REQUEST',429:'RATE_LIMITED'}.get(int(forced),'SERVICE_UNAVAILABLE'), 'Forced mock error')
        response = read(operation['response_example']) if operation.get('response_example') else None
        headers = {}
        if operation['operationId'] in ('login', 'refresh'):
            headers['Set-Cookie'] = 'ottv2_refresh=mock-refresh; HttpOnly; SameSite=Strict; Path=/api/v1/auth'
        if operation['operationId'] == 'logout':
            headers['Set-Cookie'] = 'ottv2_refresh=; HttpOnly; SameSite=Strict; Path=/api/v1/auth; Max-Age=0'
        if operation['response'] == 'SignedUrl':
            response['url'] = f'http://127.0.0.1:{self.server.server_port}/fixtures/replay.json'
        self.respond(operation['status'], response, headers)

    do_GET = do_POST = do_PUT = do_PATCH = handle_request

    def log_message(self, fmt, *args):
        pass  # Do not log credentials/request bodies.


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4010)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Stateless contract mock: http://127.0.0.1:{server.server_port}; Ctrl+C to stop', flush=True)
    server.serve_forever()

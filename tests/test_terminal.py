"""Real loopback WebSockets and PTYs; PAM is mocked only to create test logins."""
import json
import logging
import os
import re
import psutil
import threading
import time
import unittest
from unittest.mock import patch

import websocket
from websocket import WebSocketConnectionClosedException as ConnectionClosed
from websocket import WebSocketBadStatusException as ConnectionError


class Client:
    def __init__(self, url, headers):
        self.socket = websocket.create_connection(url, origin=headers.get('Origin'),
            header={k: v for k, v in headers.items() if k != 'Origin'}, timeout=3)

    def send(self, message):
        self.socket.send(message)

    def receive(self, timeout=3):
        self.socket.settimeout(timeout)
        try:
            value = self.socket.recv()
        except websocket.WebSocketTimeoutException:
            return None
        if value == '':
            raise ConnectionClosed()
        return value

    def close(self):
        self.socket.close(timeout=0.2)
from werkzeug.serving import make_server

import app as module
import terminal_service


class TerminalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module.app.config.update(TESTING=True, SECRET_KEY='isolated-test-key')
        cls.server = make_server('127.0.0.1', 0, module.app, threaded=True)
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'
        cls.url = f'ws://127.0.0.1:{cls.server.server_port}/ws/terminal'
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.client = module.app.test_client()
        module.attempts.clear()
        self.sockets = []
        self.client.get('/login')
        with self.client.session_transaction() as session:
            csrf = session['csrf']
        with patch.object(module, 'authenticate', return_value=True):
            response = self.client.post('/login', data=dict(username=module.allowed_user, password='fixture', csrf=csrf))
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.csrf = session['csrf']
            self.login_id = session['login_id']
        self.cookie = self.client.get_cookie('session').value

    def tearDown(self):
        for ws in self.sockets:
            try:
                ws.close()
            except ConnectionClosed:
                pass
        with module.login_lock:
            lease = module.login_sessions.pop(self.login_id, None)
            if lease:
                lease['revoked'].set()
        deadline = time.monotonic() + 3
        while self.login_id in module.terminals.active and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertNotIn(self.login_id, module.terminals.active)

    def connect(self, origin=None, token=None, **size):
        ws = Client(self.url, headers={'Origin': origin or self.origin, 'Cookie': 'session=' + self.cookie})
        self.sockets.append(ws)
        ws.send(json.dumps(dict(type='open', csrf=token if token is not None else self.csrf, cols=80, rows=24) | size))
        return ws

    def receive(self, ws):
        raw = ws.receive(timeout=3)
        self.assertIsNotNone(raw, 'Timed out waiting for terminal frame')
        return json.loads(raw)

    def output_until(self, ws, needle):
        output = ''
        deadline = time.monotonic() + 6
        while needle not in output and time.monotonic() < deadline:
            message = self.receive(ws)
            if message['type'] == 'output':
                output += message['data']
            else:
                self.fail(str(message))
        self.assertIn(needle, output)
        return output

    def test_anonymous_and_unsigned_cookie_rejected(self):
        with self.assertRaises(ConnectionError):
            Client(self.url, headers={'Origin': self.origin})
        with self.assertRaises(ConnectionError):
            Client(self.url, headers={'Origin': self.origin, 'Cookie': 'session=invalid'})

    def test_wrong_origin_rejected_before_shell(self):
        with patch.object(terminal_service, 'Shell') as shell:
            with self.assertRaises(ConnectionError):
                Client(self.url, headers={'Origin': 'http://untrusted.invalid', 'Cookie': 'session=' + self.cookie})
            shell.assert_not_called()

    def test_csrf_and_size_rejected_before_shell(self):
        with patch.object(terminal_service, 'Shell') as shell:
            self.assertEqual(self.receive(self.connect(token='wrong'))['type'], 'error')
            self.assertEqual(self.receive(self.connect(cols=9999))['type'], 'error')
            shell.assert_not_called()

    def test_real_shell_input_resize_and_exit(self):
        ws = self.connect()
        self.assertEqual(self.receive(ws)['type'], 'ready')
        ws.send(json.dumps(dict(type='input', data="printf '\\nDRIFT_%s\\n' OS_READY\r")))
        self.output_until(ws, 'DRIFT_OS_READY')
        ws.send(json.dumps(dict(type='resize', cols=101, rows=33)))
        ws.send(json.dumps(dict(type='input', data="stty size; printf '\\nSIZE_%s\\n' DONE\r")))
        output = self.output_until(ws, 'SIZE_DONE')
        self.assertIn('33 101', output)
        ws.send(json.dumps(dict(type='input', data='exit\r')))
        while self.receive(ws)['type'] != 'exit':
            pass

    def test_duplicate_and_global_limit(self):
        ws = self.connect()
        self.assertEqual(self.receive(ws)['type'], 'ready')
        self.assertIn('already', self.receive(self.connect())['message'])
        with patch.object(terminal_service, 'MAX_TERMINALS', 0):
            other_id = 'fixture-other-login'
            with module.login_lock:
                original = module.login_sessions[self.login_id]
                module.login_sessions[other_id] = original
            try:
                with self.client.session_transaction() as session:
                    session['login_id'] = other_id
                old_cookie = self.cookie
                self.cookie = self.client.get_cookie('session').value
                self.assertIn('slots', self.receive(self.connect())['message'])
                self.cookie = old_cookie
            finally:
                with module.login_lock:
                    module.login_sessions.pop(other_id, None)

    def test_logout_closes_shell_and_revokes_copied_cookie(self):
        ws = self.connect()
        self.assertEqual(self.receive(ws)['type'], 'ready')
        self.client.post('/logout', data=dict(csrf=self.csrf))
        while True:
            message = self.receive(ws)
            if message['type'] == 'exit':
                self.assertIn('session ended', message['message'])
                break
        with self.assertRaises(ConnectionError):
            Client(self.url, headers={'Origin': self.origin, 'Cookie': 'session=' + self.cookie})

    def test_expiry_and_idle_timeout(self):
        with module.login_lock:
            module.login_sessions[self.login_id]['expires'] = time.time() - 1
        self.assertEqual(self.client.get('/terminal').status_code, 302)
        with self.assertRaises(ConnectionError):
            Client(self.url, headers={'Origin': self.origin, 'Cookie': 'session=' + self.cookie})
        with module.login_lock:
            module.login_sessions[self.login_id]['expires'] = time.time() + 2
        ws = self.connect()
        self.assertEqual(self.receive(ws)['type'], 'ready')
        while self.receive(ws)['type'] != 'exit':
            pass
        with module.login_lock:
            module.login_sessions[self.login_id]['expires'] = time.time() + 3600
        deadline = time.monotonic() + 2
        while self.login_id in module.terminals.active and time.monotonic() < deadline:
            time.sleep(0.02)
        with patch.object(terminal_service, 'IDLE_SECONDS', 0):
            ws = self.connect()
            self.assertEqual(self.receive(ws)['type'], 'ready')
            self.assertIn('without keyboard', self.receive(ws)['message'])

    def test_malformed_and_oversized_input(self):
        ws = self.connect()
        self.assertEqual(self.receive(ws)['type'], 'ready')
        ws.send(json.dumps(dict(type='input', data='a' * 5000)))
        while True:
            message = self.receive(ws)
            if message['type'] == 'error':
                self.assertIn('too large', message['message'])
                break

    def test_interrupt_and_child_cleanup_on_disconnect(self):
        ws = self.connect()
        self.assertEqual(self.receive(ws)['type'], 'ready')
        ws.send(json.dumps(dict(type='input', data='sleep 30\r')))
        self.output_until(ws, 'sleep 30')
        time.sleep(0.1)
        ws.send(json.dumps(dict(type='input', data="\x03printf '\\nINTERRUPT_%s\\n' OK\r")))
        self.output_until(ws, 'INTERRUPT_OK')
        ws.send(json.dumps(dict(type='input', data="sleep 30 & printf '\\nCHILD_%s\\n' \"$!\"\r")))
        output = ''
        while not re.search(r'CHILD_(\d+)', output):
            message = self.receive(ws)
            if message['type'] == 'output':
                output += message['data']
        child = psutil.Process(int(re.search(r'CHILD_(\d+)', output).group(1)))
        ws.close()
        deadline = time.monotonic() + 3
        while self.login_id in module.terminals.active and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertNotIn(self.login_id, module.terminals.active)
        self.assertFalse(child.is_running() and child.status() != psutil.STATUS_ZOMBIE)

    def test_page_and_csp(self):
        with self.client.get('/terminal') as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'/static/vendor/xterm.js', response.data)
            self.assertIn("script-src 'self'", response.headers['Content-Security-Policy'])
        for path in ['/static/vendor/xterm.js', '/static/vendor/xterm.css', '/static/vendor/addon-fit.js', '/static/terminal.js']:
            with self.client.get(path) as response:
                self.assertEqual(response.status_code, 200)


class ShellTest(unittest.TestCase):
    def test_identity_and_service_secrets(self):
        with patch.dict(os.environ, {'DRIFTOS_SECRET_KEY': 'not-in-child', 'WIKISTREAM_API_TOKEN': 'not-in-child'}):
            shell = terminal_service.Shell(module.allowed_user, 80, 24)
        try:
            environment = psutil.Process(shell.process.pid).environ()
            self.assertNotIn('DRIFTOS_SECRET_KEY', environment)
            self.assertNotIn('WIKISTREAM_API_TOKEN', environment)
            self.assertEqual(environment['USER'], module.allowed_user)
            self.assertEqual(os.getsid(shell.process.pid), shell.process.pid)
        finally:
            shell.close()
        self.assertIsNotNone(shell.process.poll())

    def test_root_and_different_uid_denied(self):
        with patch.object(os, 'getuid', return_value=0):
            with self.assertRaises(PermissionError):
                terminal_service.Shell(module.allowed_user, 80, 24)
        with patch.object(os, 'getuid', return_value=1234567):
            with self.assertRaises(PermissionError):
                terminal_service.Shell(module.allowed_user, 80, 24)

    def test_size_types_and_bounds(self):
        for cols, rows in [(True, 24), (80, 0), ('80', 24), (501, 24)]:
            with self.assertRaises(ValueError):
                terminal_service.dimensions(dict(cols=cols, rows=rows))


if __name__ == '__main__':
    unittest.main()

import unittest
from unittest.mock import patch
import app as module


class DriftOSTest(unittest.TestCase):
    def setUp(self):
        module.app.config.update(TESTING=True, SECRET_KEY='test-only-secret')
        module.attempts.clear()
        self.client = module.app.test_client()

    def token(self):
        self.client.get('/login')
        with self.client.session_transaction() as s:
            return s['csrf']

    def signin(self):
        with patch.object(module, 'authenticate', return_value=True):
            return self.client.post('/login', data=dict(username='test', password='fixture', csrf=self.token()))

    def test_protected_metrics_and_page(self):
        self.assertEqual(self.client.get('/api/stats').status_code, 401)
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_csrf(self):
        self.assertEqual(self.client.post('/login', data={'username': 'test'}).status_code, 403)

    def test_failed_login_and_rate_limit(self):
        token = self.token()
        with patch.object(module, 'authenticate', return_value=False):
            for _ in range(5):
                self.assertEqual(self.client.post('/login', data=dict(csrf=token)).status_code, 401)
            self.assertEqual(self.client.post('/login', data=dict(csrf=token)).status_code, 429)
        self.assertEqual(self.client.get('/api/stats').status_code, 401)

    def test_session_metrics_logout(self):
        self.assertEqual(self.signin().status_code, 302)
        self.assertEqual(self.client.get('/').status_code, 200)
        response = self.client.get('/api/stats')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertGreater(data['memory']['total'], 0)
        self.assertTrue(any(d['mount'] == '/' for d in data['drives']))
        self.assertGreaterEqual(data['cpu']['percent'], 0)
        with self.client.session_transaction() as s:
            token = s['csrf']
        self.assertEqual(self.client.post('/logout', data=dict(csrf=token)).status_code, 302)
        self.assertEqual(self.client.get('/api/stats').status_code, 401)

    def test_only_configured_nonroot_user(self):
        self.assertFalse(module.authenticate('root', 'not-a-password'))
        self.assertFalse(module.authenticate('unconfigured-user', 'not-a-password'))

    def test_headers_and_assets(self):
        for path in ['/login', '/static/app.css', '/static/app.js', '/static/driftstream.css']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
            response.close()
        response = self.client.get('/login')
        self.assertNotIn(b'value="fixture"', response.data)

    def test_metrics_failure(self):
        self.signin()
        with patch.object(module, 'collect_stats', side_effect=OSError):
            self.assertEqual(self.client.get('/api/stats').status_code, 503)


if __name__ == '__main__':
    unittest.main()

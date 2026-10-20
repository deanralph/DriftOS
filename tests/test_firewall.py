import json
import subprocess
import unittest
from unittest.mock import patch

import app as module
import firewall_backend as backend
import firewall_service as service

UFW_ACTIVE = '''Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), disabled (routed)
New profiles: skip

To                         Action      From
--                         ------      ----
22/tcp                     ALLOW IN    192.0.2.0/24
8080/tcp                   DENY IN     Anywhere
443/tcp (v6)               ALLOW IN    Anywhere (v6)
25/tcp                     REJECT OUT  Anywhere
22/tcp                     LIMIT IN    Anywhere
'''


def ufw_tools(name):
    return '/usr/bin/' + name if name in ('ufw', 'systemctl') else None


class FirewallBackendTest(unittest.TestCase):
    def test_ufw_rules_and_defaults(self):
        rules = backend.ufw_rules(UFW_ACTIVE)
        self.assertEqual(len(rules), 5)
        self.assertEqual(rules[0]['source'], '192.0.2.0/24')
        self.assertEqual(rules[2]['target'], '443/tcp (v6)')
        self.assertEqual(rules[3]['direction'], 'out')
        self.assertEqual(rules[4]['action'], 'limit')
        self.assertEqual(backend.defaults(UFW_ACTIVE), [dict(action='deny', direction='incoming'), dict(action='allow', direction='outgoing'), dict(action='disabled', direction='routed')])

    @patch.object(backend, 'executable', side_effect=ufw_tools)
    @patch.object(backend, 'run', return_value=(0, UFW_ACTIVE))
    def test_installed_active_ufw(self, run, tools):
        report = backend.report()
        self.assertEqual(report['backend'], 'ufw')
        self.assertTrue(report['active'])
        self.assertTrue(report['can_toggle'])
        self.assertEqual(len(report['revision']), 64)
        run.assert_called_once_with(['/usr/bin/ufw', 'status', 'verbose'])

    def test_inactive_ufw_saved_rules(self):
        with patch.object(backend, 'run', side_effect=[(0, 'Status: inactive'), (0, 'ufw allow 22/tcp\nufw deny from 192.0.2.1\nufw route allow 443')]):
            report = backend.ufw_report('/usr/bin/ufw')
        self.assertFalse(report['active'])
        self.assertEqual(len(report['rules']), 3)
        self.assertTrue(all(r['scope'] == 'saved' for r in report['rules']))

    def test_permission_failure_is_unknown(self):
        with patch.object(backend, 'executable', side_effect=ufw_tools), patch.object(backend, 'run', return_value=(1, 'ERROR: You need to be root to run this script')):
            report = backend.report()
        self.assertIsNone(report['active'])
        self.assertFalse(report['can_toggle'])
        self.assertEqual(report['raw'], '')

    def test_no_firewall(self):
        with patch.object(backend, 'executable', return_value=None):
            report = backend.report()
        self.assertIsNone(report['backend'])
        self.assertEqual(report['installed'], [])
        self.assertFalse(report['can_toggle'])

    def test_firewalld_active_zone_and_policy_report(self):
        results = [(0, 'running'), (0, 'public\n  interfaces: eth0'),
            (0, 'public (active)\n  target: default\n  services: ssh https\n  ports: 8080/tcp\n  icmp-blocks: echo-request\n  rich rules:\n    rule family="ipv4" source address="192.0.2.4" drop'),
            (0, 'host-policy'), (0, 'host-policy (active)\n  target: DROP')]
        with patch.object(backend, 'run', side_effect=results) as run:
            report = backend.firewalld_report('/usr/bin/firewall-cmd')
        self.assertTrue(report['active'])
        self.assertEqual(len(report['rules']), 5)
        self.assertEqual(report['rules'][-1]['action'], 'block')
        self.assertIn('target: DROP', report['raw'])
        self.assertIsNone(report['error'])
        self.assertIn(unittest.mock.call(['/usr/bin/firewall-cmd', '--zone=public', '--list-all']), run.call_args_list)

    def test_conflicting_managers_prevent_toggle(self):
        state = dict(active=True, raw='running', rules=[], policies=[], error=None)
        with patch.object(backend, 'executable', side_effect=lambda n: '/usr/bin/' + n if n in ('ufw', 'firewall-cmd') else None), patch.object(backend, 'ufw_report', return_value=state), patch.object(backend, 'firewalld_report', return_value=state):
            report = backend.report()
        self.assertTrue(report['conflict'])
        self.assertFalse(report['can_toggle'])

    def test_unknown_second_manager_prevents_toggle(self):
        active = dict(active=True, raw='running', rules=[], policies=[], error=None)
        unknown = dict(active=None, raw='', rules=[], policies=[], error='permission')
        with patch.object(backend, 'executable', side_effect=lambda n: '/usr/bin/' + n if n in ('ufw', 'firewall-cmd') else None), patch.object(backend, 'ufw_report', return_value=active), patch.object(backend, 'firewalld_report', return_value=unknown):
            self.assertFalse(backend.report()['can_toggle'])

    def test_nft_filter_chains_read_only(self):
        data = {'nftables': [{'chain':dict(family='inet', table='filter', name='input', type='filter', hook='input', policy='drop')}, {'rule':dict(family='inet',table='filter',chain='input',expr=[{'accept':None}])}]}
        with patch.object(backend, 'executable', side_effect=lambda n: '/usr/bin/nft' if n == 'nft' else None), patch.object(backend, 'run', return_value=(0, json.dumps(data))):
            report = backend.report()
        self.assertTrue(report['active'])
        self.assertFalse(report['can_toggle'])
        self.assertEqual(report['rules'][0]['action'], 'accept')
        self.assertEqual(report['policies'][0]['action'], 'drop')

    def test_iptables_both_families(self):
        with patch.object(backend, 'executable', side_effect=lambda n: '/usr/bin/' + n), patch.object(backend, 'run', side_effect=[(0, '-P INPUT DROP\n-A INPUT -p tcp --dport 22 -j ACCEPT'), (0, '-P INPUT ACCEPT')]) as run:
            report = backend.low_level_report('iptables', '/usr/bin/iptables')
        self.assertTrue(report['active'])
        self.assertEqual(len(report['policies']), 2)
        self.assertEqual(run.call_args_list[1].args[0], ['/usr/bin/ip6tables', '-S'])

    def test_firewalld_cleanup_disabled_prevents_switch(self):
        state = dict(active=True, raw='running', rules=[], policies=[], error=None)
        with patch.object(backend, 'executable', side_effect=lambda n: '/usr/bin/firewall-cmd' if n == 'firewall-cmd' else None), patch.object(backend, 'firewalld_report', return_value=state), patch.object(backend.Path, 'read_text', return_value='CleanupOnExit=no'):
            report = backend.report()
        self.assertFalse(report['can_toggle'])
        self.assertIn('cleanup on exit', report['error'])

    def test_helper_rejects_extra_or_injected_arguments_before_privileges(self):
        import contextlib
        import io
        for args in [['report', 'extra'], ['set', 'ufw; reboot', 'off', 'a'*64], ['set', 'ufw', 'off', 'a'*64, 'extra']]:
            with patch.object(backend.sys, 'argv', ['helper', *args]), patch.object(backend.os, 'geteuid') as uid, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(backend.main(), 1)
                uid.assert_not_called()

    def test_stale_state_cannot_change_firewall(self):
        with patch.object(backend, 'report', return_value=dict(backend='ufw', revision='a'*64, can_toggle=True, active=True)), patch.object(backend, 'run') as run:
            result, status = backend.set_enabled('ufw', False, 'b'*64)
        self.assertEqual(status, 409)
        run.assert_not_called()

    def test_toggle_only_fixed_command_and_verifies(self):
        before = dict(backend='ufw', revision='a'*64, can_toggle=True, active=True)
        after = dict(backend='ufw', revision='b'*64, can_toggle=True, active=False)
        with patch.object(backend, 'report', side_effect=[before, after]), patch.object(backend, 'executable', side_effect=ufw_tools), patch.object(backend, 'ufw_report', return_value=dict(active=False)), patch.object(backend, 'run', return_value=(0, 'disabled')) as run:
            result, status = backend.set_enabled('ufw', False, 'a'*64)
        self.assertEqual(status, 200)
        self.assertFalse(result['active'])
        run.assert_called_once_with(['/usr/bin/ufw', '--force', 'disable'], timeout=20)

    def test_toggle_timeout_not_retried(self):
        before = dict(backend='ufw', revision='a'*64, can_toggle=True, active=True)
        with patch.object(backend, 'report', return_value=before), patch.object(backend, 'executable', side_effect=ufw_tools), patch.object(backend, 'run', side_effect=subprocess.TimeoutExpired('ufw', 20)) as run:
            _, status = backend.set_enabled('ufw', False, 'a'*64)
        self.assertEqual(status, 503)
        self.assertEqual(run.call_count, 1)


class FirewallAPITest(unittest.TestCase):
    def setUp(self):
        module.app.config.update(TESTING=True, SECRET_KEY='firewall-test-only')
        module.attempts.clear()
        self.client = module.app.test_client()

    def signin(self):
        self.client.get('/login')
        with self.client.session_transaction() as session:
            token = session['csrf']
        with patch.object(module, 'authenticate', return_value=True):
            self.client.post('/login', data=dict(username=module.allowed_user, password='fixture', csrf=token))
        with self.client.session_transaction() as session:
            return session['csrf']

    def test_firewall_requires_login_and_csrf(self):
        self.assertEqual(self.client.get('/firewall').status_code, 302)
        self.assertEqual(self.client.get('/api/firewall').status_code, 401)
        self.signin()
        with patch.object(service, 'change') as change:
            self.assertEqual(self.client.post('/api/firewall', data=dict(enabled='false')).status_code, 403)
            change.assert_not_called()

    def test_authenticated_report_and_change(self):
        csrf = self.signin()
        with patch.object(service, 'get_report', return_value=dict(name='UFW', active=True)):
            self.assertEqual(self.client.get('/api/firewall').get_json()['name'], 'UFW')
        with patch.object(service, 'change', return_value=(dict(active=False), 200)) as change:
            response = self.client.post('/api/firewall', data=dict(csrf=csrf, backend='ufw', enabled='false', revision='a'*64))
            self.assertEqual(response.status_code, 200)
            change.assert_called_once_with('ufw', False, 'a'*64)
        self.assertEqual(self.client.get('/firewall').status_code, 200)
        self.assertNotIn(b'Your Linux shell. Right where you need it.', self.client.get('/terminal').data)

    def test_invalid_toggle_inputs_never_invoke_helper(self):
        csrf = self.signin()
        self.assertEqual(self.client.post('/api/firewall', data=dict(csrf=csrf, enabled='yes')).status_code, 400)
        with patch.object(service, 'invoke') as invoke:
            for name, enabled, rev in [('nftables', False, 'a'*64), ('ufw; reboot', True, 'a'*64), ('ufw', 'true', 'a'*64), ('ufw', True, 'shell')]:
                self.assertEqual(service.change(name, enabled, rev)[1], 400)
            invoke.assert_not_called()

    def test_no_helper_means_no_writes(self):
        with patch.object(service, 'trusted_helper', return_value=False), patch.object(service.subprocess, 'run') as run:
            self.assertEqual(service.change('ufw', False, 'a'*64)[1], 503)
            run.assert_not_called()

    def test_helper_invocation_is_fixed_and_noninteractive(self):
        output = subprocess.CompletedProcess([], 0, json.dumps(dict(status=200, data=dict(name='UFW'))))
        with patch.object(service, 'trusted_helper', return_value=True), patch.object(backend, 'executable', return_value='/usr/bin/sudo'), patch.object(service.subprocess, 'run', return_value=output) as run:
            result, status = service.invoke(['report'])
        self.assertEqual(status, 200)
        self.assertEqual(run.call_args.args[0], ['/usr/bin/sudo', '-n', '--', '/usr/local/libexec/driftos-firewall', 'report'])
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_unprivileged_detection_is_labelled(self):
        with patch.object(service, 'invoke', return_value=(None,503)), patch.object(backend, 'report', return_value=dict(backend='ufw', active=None, can_toggle=True)):
            report = service.get_report()
        self.assertFalse(report['can_toggle'])
        self.assertFalse(report['privileged'])
        self.assertTrue(report['setup_required'])


if __name__ == '__main__':
    unittest.main()

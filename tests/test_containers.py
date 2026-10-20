import json
import subprocess
import unittest
from unittest.mock import patch

import app as module
import containers_service as service


class RuntimeTests(unittest.TestCase):
    def test_docker_json_lines_allowlisted(self):
        raw = '\n'.join(json.dumps(dict(ID='a'*64, Names=name, Image='nginx:alpine', State='running', Status='Up', Ports='80/tcp', Networks='bridge', Secret='hidden')) for name in ('web','api'))
        with patch.object(service,'command',return_value=raw):
            result=service.inventory('docker','containers')
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['name'],'web')
        self.assertNotIn('Secret',result[0])

    def test_podman_array_lowercase_and_ports(self):
        row=dict(Id='a'*64,Names=['web'],Image='nginx',State='running',ports=[dict(host_ip='127.0.0.1',host_port=8080,container_port=80,protocol='tcp')])
        with patch.object(service,'command',return_value=json.dumps([row])):
            result=service.inventory('podman','containers')[0]
        self.assertEqual(result['name'],'web')
        self.assertEqual(result['ports'],'127.0.0.1:8080 → 80/tcp')

    def test_other_inventories_and_empty(self):
        for kind in ('images','volumes','networks'):
            with self.subTest(kind=kind),patch.object(service,'command',return_value='[]'):
                self.assertEqual(service.inventory('podman',kind),[])
        with patch.object(service,'command',return_value='{"Name":"data","Driver":"local"}'):
            self.assertEqual(service.inventory('docker','volumes')[0]['name'],'data')

    def test_bad_json_fails(self):
        for raw in ('broken','[1]'):
            with patch.object(service,'command',return_value=raw),self.assertRaises(service.ContainerError):service.rows('docker',['ps'])

    def test_invalid_requests_never_execute(self):
        with patch.object(service,'command') as run:
            for identifier in ('--help','abc','a'*64+';id'):
                with self.assertRaises(service.ContainerError):service.action('docker',identifier,'stop')
            with self.assertRaises(service.ContainerError):service.action('docker','a'*64,'rm')
            with self.assertRaises(service.ContainerError):service.inventory('docker','secrets')
            run.assert_not_called()
        with self.assertRaises(service.ContainerError):service.command('anything',[])

    def test_fixed_actions(self):
        with patch.object(service,'command') as run:
            service.action('docker','a'*64,'restart')
            run.assert_called_once_with('docker',['restart','--time','10','a'*64],timeout=35)

    def test_detection_distinguishes_unavailable(self):
        with patch.object(service.shutil,'which',side_effect=['/usr/bin/docker',None]),patch.object(service,'command',side_effect=service.ContainerError('Access unavailable')):
            result=service.runtimes()
        self.assertTrue(result[0]['installed']);self.assertFalse(result[0]['available'])
        self.assertEqual(result[0]['message'],'Access unavailable');self.assertFalse(result[1]['installed'])

    def test_command_does_not_inherit_remote_or_secret_environment(self):
        def run(argv, **kwargs):
            self.assertEqual(argv[:3],['/usr/bin/docker','--host','unix:///var/run/docker.sock'])
            self.assertNotIn('DOCKER_HOST',kwargs['env']);self.assertNotIn('WIKISTREAM_API_TOKEN',kwargs['env'])
            kwargs['stdout'].write(b'[]')
            return subprocess.CompletedProcess(argv,0)
        with patch.object(service.shutil,'which',return_value='/usr/bin/docker'),patch.object(service.os.path,'exists',return_value=False),patch.object(service.subprocess,'run',side_effect=run):
            self.assertEqual(service.command('docker',['ps']),'[]')

    def test_failure_and_timeout_hide_raw_errors(self):
        with patch.object(service.shutil,'which',return_value='/usr/bin/docker'),patch.object(service.subprocess,'run',return_value=subprocess.CompletedProcess([],1)):
            with self.assertRaises(service.ContainerError):service.command('docker',['ps'])
        with patch.object(service.shutil,'which',return_value='/usr/bin/docker'),patch.object(service.subprocess,'run',side_effect=subprocess.TimeoutExpired([],12)):
            with self.assertRaises(service.ContainerError) as error:service.command('docker',['ps'])
            self.assertEqual(error.exception.status,504)

    def test_logs_bounded(self):
        def run(argv,**kwargs):
            kwargs['stdout'].write(b'x'*100000);kwargs['stderr'].write(b'error')
            return subprocess.CompletedProcess(argv,0)
        with patch.object(service.shutil,'which',return_value='/usr/bin/docker'),patch.object(service.subprocess,'run',side_effect=run):
            self.assertLessEqual(len(service.logs('docker','a'*64)['log']),65536)


class RoutesTests(unittest.TestCase):
    def setUp(self):
        module.app.config.update(TESTING=True,SECRET_KEY='containers-test-only')
        self.client=module.app.test_client();module.attempts.clear()
    def login(self):
        self.client.get('/login')
        with self.client.session_transaction() as state:csrf=state['csrf']
        with patch.object(module,'authenticate',return_value=True):self.client.post('/login',data=dict(username=module.allowed_user,password='fixture',csrf=csrf))
        with self.client.session_transaction() as state:self.csrf=state['csrf']
    def test_requires_login(self):
        self.assertEqual(self.client.get('/containers').status_code,302)
        self.assertEqual(self.client.get('/api/containers/runtimes').status_code,401)
    def test_csrf_and_safe_error(self):
        self.login()
        with patch.object(service,'action') as action:
            self.assertEqual(self.client.post('/api/containers/docker/'+'a'*64+'/stop').status_code,403);action.assert_not_called()
        with patch.object(service,'inventory',side_effect=service.ContainerError('Unavailable')):
            response=self.client.get('/api/containers/docker/inventory/containers')
            self.assertEqual(response.status_code,503);self.assertEqual(response.json['error'],'Unavailable')
    def test_authenticated_page_and_action(self):
        self.login()
        self.assertEqual(self.client.get('/containers').status_code,200)
        with patch.object(service,'action',return_value=dict(message='Completed')) as action:
            response=self.client.post('/api/containers/docker/'+'a'*64+'/start',data=dict(csrf=self.csrf))
            self.assertEqual(response.status_code,200);action.assert_called_once()

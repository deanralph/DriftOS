import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, mock_open, patch

import app as module
import apps_backend as backend
import apps_service as service


class AppsBackendTest(unittest.TestCase):
    def test_native_manager_by_os_and_like(self):
        cases = [({'ID':'ubuntu','ID_LIKE':'debian'}, ['apt-get','dnf'], 'apt'),
                 ({'ID':'rocky','ID_LIKE':'rhel centos fedora'}, ['dnf','yum'], 'dnf'),
                 ({'ID':'centos'}, ['yum'], 'yum'),
                 ({'ID':'omarchy','ID_LIKE':'arch'}, ['pacman'], 'pacman'),
                 ({'ID':'fedora'}, ['dnf5','dnf'], 'dnf'),
                 ({'ID':'fedora'}, ['dnf5'], 'dnf')]
        for release, binaries, expected in cases:
            with self.subTest(release=release), patch.object(backend.platform, 'freedesktop_os_release', return_value=release), patch.object(backend, 'executable', side_effect=lambda n: '/usr/bin/'+n if n in binaries else None):
                self.assertEqual(backend.detect()['manager'], expected)

    def test_foreign_manager_not_selected(self):
        for release in [{'ID':'ubuntu'}, {'ID':'nixos'}]:
            with patch.object(backend.platform, 'freedesktop_os_release', return_value=release), patch.object(backend,'executable', side_effect=lambda n: '/usr/bin/dnf' if n == 'dnf' else None):
                self.assertIsNone(backend.detect()['manager'])

    def test_package_mapping_and_commands(self):
        with patch.object(backend, 'executable', side_effect=lambda n:'/usr/bin/'+n):
            self.assertEqual(backend.commands('apt','openssh'), [['/usr/bin/apt-get','update'],['/usr/bin/apt-get','-y','--no-remove','install','--','openssh-server']])
            self.assertEqual(backend.commands('dnf','samba'), [['/usr/bin/dnf','-y','install','--','samba']])
            self.assertEqual(backend.commands('yum','btop'), [['/usr/bin/yum','-y','install','--','btop']])
            self.assertEqual(backend.commands('pacman','openssh'), [['/usr/bin/pacman','-S','--needed','--noconfirm','--','openssh']])
            with self.assertRaises(ValueError):
                backend.commands('apt','btop; reboot')

    def test_package_database_states(self):
        cases=[('apt',0,'ii \t1.2',True,'1.2'),('apt',0,'rc \t1.2',False,None),
               ('apt',1,'dpkg-query: no packages found matching btop',False,None),
               ('dnf',0,'1.2-3',True,'1.2-3'),('yum',1,'package btop is not installed',False,None),
               ('pacman',0,'btop 1.2-3',True,'1.2-3'),('pacman',1,"error: package 'btop' was not found",False,None),
               ('pacman',1,'database error',None,None)]
        for manager,code,output,installed,version in cases:
            with self.subTest(manager=manager,output=output), patch.object(backend,'executable', side_effect=lambda n:'/usr/bin/'+n), patch.object(backend,'run',return_value=(code,output)):
                self.assertEqual(backend.package_state(manager,'btop'),(installed,version))

    def test_missing_db_and_timeouts_unknown(self):
        with patch.object(backend,'executable',return_value=None):
            self.assertEqual(backend.package_state('apt','btop'),(None,None))
        with patch.object(backend,'executable',return_value='/usr/bin/pacman'), patch.object(backend,'run',side_effect=__import__('subprocess').TimeoutExpired('pacman',2)):
            self.assertEqual(backend.package_state('pacman','btop'),(None,None))

    def test_catalog_status(self):
        with patch.object(backend,'detect',return_value=dict(manager='apt',os='Ubuntu',error=None)), patch.object(backend,'package_state',return_value=(False,None)):
            report=backend.report()
        self.assertEqual(len(report['apps']),6)
        ssh=next(x for x in report['apps'] if x['id']=='openssh')
        self.assertEqual(ssh['package'],'openssh-server')
        self.assertIn('start it automatically',ssh['note'])

    def test_submit_stale_manager_or_installed_never_spawns(self):
        with patch.object(backend,'detect',return_value=dict(manager='pacman')), patch.object(backend.subprocess,'Popen') as popen:
            self.assertEqual(backend.submit('btop','apt')[1],409)
            with patch.object(backend,'package_state',return_value=(True,'1')):
                self.assertEqual(backend.submit('btop','pacman')[1],409)
            with patch.object(backend,'package_state',return_value=(None,None)):
                self.assertEqual(backend.submit('btop','pacman')[1],409)
            popen.assert_not_called()

    def test_submit_persists_and_passes_lock_to_detached_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_open=mock_open();fake_open.return_value.fileno.return_value=42
            with patch.object(backend,'STATE_DIR',Path(directory)), patch.object(backend,'detect',return_value=dict(manager='pacman')), patch.object(backend,'package_state',return_value=(False,None)), patch.object(backend,'open',fake_open,create=True), patch.object(backend.fcntl,'flock'), patch.object(backend.subprocess,'Popen') as popen:
                job,status=backend.submit('btop','pacman')
                self.assertEqual(status,202)
                stored=json.loads((Path(directory)/(job['id']+'.json')).read_text())
                self.assertEqual(stored['state'],'queued')
                self.assertEqual(popen.call_args.kwargs['pass_fds'],(42,))
                self.assertTrue(popen.call_args.kwargs['start_new_session'])
                self.assertIn('worker',popen.call_args.args[0])
                # A queued operation prevents immediate duplicate submissions.
                self.assertEqual(backend.submit('btop','pacman')[1],409)

    def test_busy_install_lock(self):
        with patch.object(backend,'detect',return_value=dict(manager='apt')), patch.object(backend,'package_state',return_value=(False,None)), patch.object(backend,'open',mock_open(),create=True), patch.object(backend.fcntl,'flock',side_effect=BlockingIOError), patch.object(backend.subprocess,'Popen') as popen:
            self.assertEqual(backend.submit('btop','apt')[1],409)
            popen.assert_not_called()

    def test_worker_records_log_and_verifies_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            job_id='a'*32
            job=dict(id=job_id,app='btop',package='btop',manager='pacman',state='queued',created_at=int(time.time()),updated_at=int(time.time()),log='')
            process=MagicMock();process.pid=12345;process.stdout=io.BytesIO(b'downloading\ninstalled btop\n');process.wait.return_value=0;process.poll.return_value=0
            fd=os.open(Path(directory)/'lock',os.O_CREAT|os.O_RDWR,0o600)
            with patch.object(backend,'STATE_DIR',Path(directory)), patch.object(backend,'detect',return_value=dict(manager='pacman')), patch.object(backend,'executable',side_effect=lambda n:'/usr/bin/'+n), patch.object(backend,'package_state',return_value=(True,'1.2-3')), patch.object(backend.subprocess,'Popen',return_value=process) as popen:
                backend.atomic_job(job)
                backend.worker(job_id,fd)
                result=backend.public_job(job_id)
            self.assertEqual(result['state'],'succeeded')
            self.assertIn('installed btop',result['log'])
            self.assertNotIn('worker_pid',result)
            self.assertNotIn('WIKISTREAM_API_TOKEN',popen.call_args.kwargs['env'])
            self.assertEqual(popen.call_args.args[0],['/usr/bin/pacman','-S','--needed','--noconfirm','--','btop'])

    def test_worker_native_failure_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            job_id='b'*32
            process=MagicMock();process.pid=12345;process.stdout=io.BytesIO(b'failed to download package\n');process.wait.return_value=1;process.poll.return_value=1
            fd=os.open(Path(directory)/'lock',os.O_CREAT|os.O_RDWR,0o600)
            with patch.object(backend,'STATE_DIR',Path(directory)), patch.object(backend,'detect',return_value=dict(manager='pacman')), patch.object(backend,'executable',side_effect=lambda n:'/usr/bin/'+n), patch.object(backend.subprocess,'Popen',return_value=process) as popen:
                backend.atomic_job(dict(id=job_id,app='btop',package='btop',manager='pacman',state='queued',created_at=1,updated_at=1,log=''))
                backend.worker(job_id,fd)
                result=backend.public_job(job_id)
            self.assertEqual(result['state'],'failed')
            self.assertEqual(popen.call_count,1)

    def test_job_identity_and_traversal(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(backend,'STATE_DIR',Path(directory)), patch.object(backend,'process_identity',return_value=None):
            job_id='c'*32
            backend.atomic_job(dict(id=job_id,state='running',worker_pid=999999,worker_start='1',created_at=1))
            self.assertEqual(backend.public_job(job_id)['state'],'unknown')
            with self.assertRaises(ValueError):
                backend.public_job('../etc/shadow')

    def test_helper_rejects_extra_args_and_arbitrary_packages(self):
        for args in [['install','curl','apt'],['install','btop','apt','--extra'],['job','../../etc/shadow'],['install','btop','apt; reboot']]:
            with patch.object(backend.sys,'argv',['helper',*args]), patch.object(backend.os,'geteuid') as uid, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(backend.main(),1)
                uid.assert_not_called()

    def test_log_redaction(self):
        text='https://user:password@example.org/repo?token=secret&ok=yes'
        result=backend.redact(text)
        self.assertNotIn('password',result)
        self.assertNotIn('secret',result)


class AppsAPITest(unittest.TestCase):
    def setUp(self):
        module.app.config.update(TESTING=True,SECRET_KEY='apps-test-only')
        module.attempts.clear();self.client=module.app.test_client()

    def signin(self):
        self.client.get('/login')
        with self.client.session_transaction() as session: token=session['csrf']
        with patch.object(module,'authenticate',return_value=True):
            self.client.post('/login',data=dict(csrf=token,username=module.allowed_user,password='fixture'))
        with self.client.session_transaction() as session: return session['csrf']

    def test_login_and_csrf_boundaries(self):
        self.assertEqual(self.client.get('/apps').status_code,302)
        self.assertEqual(self.client.get('/api/apps').status_code,401)
        self.assertEqual(self.client.get('/api/apps/jobs/'+'a'*32).status_code,401)
        self.signin()
        with patch.object(service,'install') as install:
            self.assertEqual(self.client.post('/api/apps/install',data=dict(app='btop')).status_code,403)
            install.assert_not_called()

    def test_report_install_and_job_routes(self):
        csrf=self.signin()
        self.assertEqual(self.client.get('/apps').status_code,200)
        with patch.object(service,'get_report',return_value=dict(manager='pacman')):
            self.assertEqual(self.client.get('/api/apps').get_json()['manager'],'pacman')
        with patch.object(service,'install',return_value=(dict(id='a'*32,state='queued'),202)) as install:
            self.assertEqual(self.client.post('/api/apps/install',data=dict(csrf=csrf,app='btop',manager='pacman')).status_code,202)
            install.assert_called_once_with('btop','pacman')
        with patch.object(service,'get_job',return_value=(dict(state='succeeded'),200)):
            self.assertEqual(self.client.get('/api/apps/jobs/'+'a'*32).get_json()['state'],'succeeded')

    def test_unconfigured_helper_no_install(self):
        with patch.object(service,'trusted_helper',return_value=False), patch.object(service.subprocess,'run') as run:
            self.assertEqual(service.install('btop','pacman')[1],503)
            run.assert_not_called()

    def test_bad_inputs_no_helper_invocation(self):
        with patch.object(service,'invoke') as invoke:
            self.assertEqual(service.install('arbitrary-package','apt')[1],400)
            self.assertEqual(service.install('btop','shell')[1],400)
            self.assertEqual(service.get_job('not-a-job')[1],400)
            invoke.assert_not_called()

    def test_unprivileged_report_has_setup_and_installed_status(self):
        with patch.object(service,'invoke',return_value=(dict(error='no access'),503)), patch.object(backend,'report',return_value=dict(manager='pacman',apps=[])):
            report=service.get_report()
        self.assertFalse(report['can_install'])
        self.assertTrue(report['setup_required'])
        self.assertIn('install-apps-helper.sh',report['setup_command'])


if __name__=='__main__': unittest.main()

import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import app as module
import shares_backend as backend
import shares_service as bridge


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.state=dict(shares=[],users=[dict(name='alex',enabled=True,pending=False)])
    def request(self,**extra):
        return dict(name='documents',protocol='smb',read_only=True,enabled=True,users=['alex'],**extra)
    def test_names_and_injection(self):
        for name in ('../etc','global\npath=x','root;id','a'*21,'-bad','UPPER',''):
            with self.subTest(name=name),self.assertRaises(backend.ShareError):backend.name(name)
        self.assertEqual(backend.name('team_docs'),'team_docs')
    def test_password_constraints(self):
        for secret in ('short','x'*129,'x'*12+'\n','x'*12+'\0'):
            with self.assertRaises(backend.ShareError):backend.password(secret)
        self.assertEqual(backend.password('fixture-only-password'),'fixture-only-password')
    def test_smb_requires_known_provisioned_users(self):
        data=self.request();self.assertEqual(backend.share_request(data,self.state)['users'],['alex'])
        for users in ([],['root'],['../root'],[{}]):
            data['users']=users
            with self.assertRaises(backend.ShareError):backend.share_request(data,self.state)
        self.state['users'][0]['pending']=True
        with self.assertRaises(backend.ShareError):backend.share_request(self.request(),self.state)
    def test_nfs_explicit_clients_only(self):
        data=dict(name='backups',protocol='nfs',read_only=True,enabled=True,clients='192.168.1.42, 192.168.1.0/24,2001:db8::1')
        result=backend.share_request(data,self.state)
        self.assertIn('192.168.1.42/32',result['clients']);self.assertEqual(result['users'],[])
        for clients in ('*','0.0.0.0/0','::/0','host.example','192.168.1.0/24(rw,no_root_squash)',''):
            data['clients']=clients
            with self.assertRaises(backend.ShareError):backend.share_request(data,self.state)
    def test_strict_boolean(self):
        data=self.request();data['enabled']='false'
        with self.assertRaises(backend.ShareError):backend.share_request(data,self.state)
    def test_render_no_guest_no_root_squash_no_arbitrary_paths(self):
        state=dict(users=[],shares=[backend.share_request(self.request(),self.state),dict(name='backup',protocol='nfs',enabled=True,read_only=False,clients=['192.168.1.0/24'],users=[])])
        with patch.object(backend.grp,'getgrnam',return_value=SimpleNamespace(gr_gid=12345)):
            smb,nfs=backend.render(state)
        self.assertIn('[ds_documents]',smb);self.assertIn('valid users = ds_u_alex',smb);self.assertIn('guest ok = no',smb);self.assertIn('follow symlinks = no',smb)
        self.assertIn('all_squash,anonuid=65534,anongid=12345',nfs);self.assertNotIn('no_root_squash',nfs)
        state['shares'][0]['enabled']=False
        with patch.object(backend.grp,'getgrnam',return_value=SimpleNamespace(gr_gid=12345)):
            self.assertNotIn('[ds_documents]',backend.render(state)[0])
    def test_stale_revision_no_mutation(self):
        with patch.object(backend,'revision',return_value='current'),patch.object(backend,'apply_share') as apply:
            with self.assertRaises(backend.ShareError) as error:backend.dispatch('share',{'revision':'old'},self.state)
            self.assertEqual(error.exception.status,409);apply.assert_not_called()
    def test_cli_rejects_extra_arguments_without_commands(self):
        with patch.object(backend.sys,'argv',['helper','user','--anything']),patch.object(backend,'run') as run:
            with self.assertRaises(backend.ShareError):backend.main()
            run.assert_not_called()


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.paths=[]
        for attr,child in [('STATE_DIR','state'),('ROOT','folders'),('SMB','smb.conf'),('NFS','exports'),('MAIN','main.conf')]:
            value=self.root/child
            if attr in ('STATE_DIR','ROOT'):value.mkdir()
            else:value.write_text('old-config')
            p=patch.object(backend,attr,value);p.start();self.paths.append(p)
        self.trusted=patch.object(backend,'trusted');self.trusted.start()
        self.state=dict(shares=[],users=[dict(name='alex',account='ds_u_alex',enabled=True,pending=False)])
        self.services=dict(smb=dict(installed=True,active=True,service='smb.service'),nfs=dict(installed=True,active=True,service='nfs-server.service'))
    def tearDown(self):
        self.trusted.stop()
        for p in self.paths:p.stop()
        self.temp.cleanup()
    def command(self,args,**kwargs):
        output=''
        if '--parameter-name=server role' in args:output='standalone server'
        elif '--parameter-name=passdb backend' in args:output='tdbsam'
        elif '--parameter-name=unix password sync' in args:output='No'
        elif args[:2]==['testparm','-s']:output='[global]\n[ds_documents]\n'
        return subprocess.CompletedProcess(args,0,output)
    def existing(self):
        share=dict(name='documents',protocol='smb',enabled=True,read_only=True,users=['alex'],clients=[])
        self.state['shares']=[share];folder=backend.ROOT/'documents';folder.mkdir()
        return share
    def test_atomic_state_and_previous(self):
        backend.save(self.state);backend.save(dict(self.state,users=[]))
        self.assertEqual(json.loads((backend.STATE_DIR/'state.previous.json').read_text())['users'][0]['name'],'alex')
        self.assertEqual((backend.STATE_DIR/'state.json').stat().st_mode & 0o777,0o600)
    def test_revision_tracks_external_configuration(self):
        old=backend.revision(self.state);backend.MAIN.write_text('external-change');self.assertNotEqual(old,backend.revision(self.state))
    def test_edit_reloads_and_retains_data(self):
        share=self.existing();(backend.ROOT/'documents'/'kept.txt').write_text('data')
        original=Path.lstat
        def info(path,*args,**kwargs):
            if path==backend.ROOT/'documents':return SimpleNamespace(st_mode=0o42770,st_uid=0,st_gid=123)
            return original(path,*args,**kwargs)
        with patch.object(backend,'detection',return_value=self.services),patch.object(backend,'run',side_effect=self.command) as run,patch.object(backend.grp,'getgrnam',return_value=SimpleNamespace(gr_gid=123,gr_mem=['ds_u_alex'])),patch.object(Path,'lstat',info):
            backend.apply_share(dict(share,read_only=False),self.state)
        self.assertTrue((backend.ROOT/'documents'/'kept.txt').exists());self.assertIn('read only = no',backend.SMB.read_text())
        self.assertIn(['systemctl','reload','smb.service'],[call.args[0] for call in run.call_args_list])
    def test_reload_failure_restores_definition_and_members(self):
        share=self.existing();original=Path.lstat
        def info(path,*args,**kwargs):
            if path==backend.ROOT/'documents':return SimpleNamespace(st_mode=0o42770,st_uid=0,st_gid=123)
            return original(path,*args,**kwargs)
        calls=[]
        def command(args,**kwargs):
            calls.append(args)
            if args[:2]==['systemctl','reload'] and calls.count(args)==1:raise backend.ShareError('fixture reload failed',503)
            return self.command(args,**kwargs)
        with patch.object(backend,'detection',return_value=self.services),patch.object(backend,'run',side_effect=command),patch.object(backend.grp,'getgrnam',return_value=SimpleNamespace(gr_gid=123,gr_mem=['ds_u_alex'])),patch.object(Path,'lstat',info):
            with self.assertRaises(backend.ShareError):backend.apply_share(dict(share,read_only=False),self.state)
        self.assertEqual(backend.SMB.read_text(),'old-config')
        self.assertIn(['gpasswd','-M','ds_u_alex','ds_s_documents'],calls)
    def test_preexisting_directory_not_adopted(self):
        (backend.ROOT/'documents').mkdir()
        with patch.object(backend,'detection',return_value=self.services),patch.object(backend,'run',side_effect=lambda args,**kwargs: subprocess.CompletedProcess(args,0,'standalone server' if 'role' in ' '.join(args) else 'tdbsam' if 'backend' in ' '.join(args) else '[global]')):
            with self.assertRaises(backend.ShareError):backend.apply_share(dict(name='documents',protocol='smb',enabled=True,read_only=True,users=['alex']),self.state)
    def test_password_only_on_stdin_never_state(self):
        secret='disposable-test-password';calls=[]
        def command(args,**kwargs):calls.append((args,kwargs));return self.command(args,**kwargs)
        with patch.object(backend,'run',side_effect=command),patch.object(backend,'executable',return_value='/usr/bin/tool'),patch.object(backend.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=998,pw_shell='/usr/bin/nologin')):
            backend.user_change(dict(name='alex',action='password',password=secret),self.state)
        self.assertFalse(any(secret in str(args) for args,_ in calls));self.assertTrue(any(kwargs.get('input')==secret+'\n'+secret+'\n' for _,kwargs in calls))
        self.assertNotIn(secret,(backend.STATE_DIR/'state.json').read_text())
    def test_user_disable_does_not_change_linux_password_or_groups(self):
        with patch.object(backend,'run',side_effect=self.command) as run,patch.object(backend,'executable',return_value='/usr/bin/tool'),patch.object(backend.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=998,pw_shell='/usr/bin/nologin')):
            backend.user_change(dict(name='alex',action='disable'),self.state)
        self.assertIn(['smbpasswd','-d','ds_u_alex'],[call.args[0] for call in run.call_args_list]);self.assertFalse(self.state['users'][0]['enabled'])
    def test_unmanaged_users_never_modified(self):
        with patch.object(backend,'run') as run:
            with self.assertRaises(backend.ShareError):backend.user_change(dict(name='root',action='disable'),self.state)
            run.assert_not_called()
    def test_domain_backend_rejected(self):
        with patch.object(backend,'executable',return_value='/usr/bin/tool'),patch.object(backend,'run',return_value=subprocess.CompletedProcess([],0,'active directory domain controller')):
            with self.assertRaises(backend.ShareError):backend.user_change(dict(name='alex',action='disable'),self.state)
    def test_new_nfs_folder_and_config_without_starting_service(self):
        request=dict(name='backups',protocol='nfs',enabled=True,read_only=True,clients='192.168.2.0/24')
        services=copy.deepcopy(self.services);services['nfs']['active']=False
        lookups=[KeyError('absent'),SimpleNamespace(gr_gid=123,gr_mem=[]),SimpleNamespace(gr_gid=123,gr_mem=[]),SimpleNamespace(gr_gid=123,gr_mem=[])]
        with patch.object(backend,'detection',return_value=services),patch.object(backend,'run',side_effect=self.command) as run,patch.object(backend.grp,'getgrnam',side_effect=lookups),patch.object(backend.os,'chown'):
            backend.apply_share(request,self.state)
        self.assertTrue((backend.ROOT/'backups').is_dir());self.assertIn('192.168.2.0/24(ro,sync,subtree_check,all_squash',backend.NFS.read_text())
        self.assertTrue(json.loads((backend.STATE_DIR/'state.json').read_text())['shares'][0]['enabled'])
        self.assertFalse(any(call.args[0][0] in ('systemctl','exportfs') for call in run.call_args_list))
    def test_create_no_login_user_and_never_adopt_existing(self):
        secret='fixture-only-password'
        with patch.object(backend,'run',side_effect=self.command) as run,patch.object(backend,'executable',return_value='/usr/bin/nologin'),patch.object(backend.pwd,'getpwnam',side_effect=[KeyError('absent'),SimpleNamespace(pw_uid=998,pw_shell='/usr/bin/nologin')]):
            backend.user_change(dict(name='newperson',action='create',password=secret),self.state)
        create=next(call.args[0] for call in run.call_args_list if call.args[0][0]=='useradd')
        self.assertIn('--no-create-home',create);self.assertIn('/usr/bin/nologin',create)
        self.assertEqual(create[-1],'ds_u_newperson');self.assertNotIn(secret,json.dumps(self.state))
        self.assertFalse(self.state['users'][-1]['pending'])
        with patch.object(backend,'run',side_effect=self.command) as run,patch.object(backend,'executable',return_value='/usr/bin/nologin'),patch.object(backend.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1000)):
            with self.assertRaises(backend.ShareError):backend.user_change(dict(name='existing',action='create',password=secret),self.state)
            self.assertFalse(any(call.args[0][0]=='useradd' for call in run.call_args_list))
    def test_failed_smb_provision_keeps_pending_account_recoverable(self):
        def command(args,**kwargs):
            if args[0]=='smbpasswd':raise backend.ShareError('fixture password setup failed',503)
            return self.command(args,**kwargs)
        with patch.object(backend,'run',side_effect=command),patch.object(backend,'executable',return_value='/usr/bin/nologin'),patch.object(backend.pwd,'getpwnam',side_effect=[KeyError('absent'),SimpleNamespace(pw_uid=998,pw_shell='/usr/bin/nologin')]):
            with self.assertRaises(backend.ShareError):backend.user_change(dict(name='pending',action='create',password='fixture-only-password'),self.state)
        saved=json.loads((backend.STATE_DIR/'state.json').read_text())['users'][-1]
        self.assertTrue(saved['pending']);self.assertFalse(saved['enabled'])
    def test_protocol_change_rejected_before_commands(self):
        share=self.existing()
        with patch.object(backend,'run') as run:
            with self.assertRaises(backend.ShareError):backend.apply_share(dict(share,protocol='nfs',clients='192.168.1.0/24'),self.state)
            run.assert_not_called()

    def test_unix_password_sync_blocks_password_changes(self):
        def command(args,**kwargs):
            if '--parameter-name=unix password sync' in args:return subprocess.CompletedProcess(args,0,'Yes')
            return self.command(args,**kwargs)
        with patch.object(backend,'run',side_effect=command) as run,patch.object(backend,'executable',return_value='/usr/bin/tool'):
            with self.assertRaises(backend.ShareError):backend.user_change(dict(name='alex',action='password',password='fixture-only-password'),self.state)
            self.assertFalse(any(call.args[0][0]=='smbpasswd' for call in run.call_args_list))

    def test_start_uses_fixed_service_no_enable_boot(self):
        with patch.object(backend,'revision',return_value='current'),patch.object(backend,'detection',return_value=self.services),patch.object(backend,'run',side_effect=self.command) as run:
            backend.dispatch('start',dict(revision='current',protocol='nfs'),self.state)
        self.assertEqual([call.args[0] for call in run.call_args_list],[['systemctl','start','nfs-server.service'],['exportfs','-ra']])


class RouteTests(unittest.TestCase):
    def setUp(self):
        module.app.config.update(TESTING=True,SECRET_KEY='shares-test-only');module.attempts.clear();self.client=module.app.test_client()
    def login(self):
        self.client.get('/login')
        with self.client.session_transaction() as state:csrf=state['csrf']
        with patch.object(module,'authenticate',return_value=True):self.client.post('/login',data=dict(username=module.allowed_user,password='fixture',csrf=csrf))
        with self.client.session_transaction() as state:self.csrf=state['csrf']
    def test_login_and_csrf(self):
        self.assertEqual(self.client.get('/shares').status_code,302);self.assertEqual(self.client.get('/api/shares').status_code,401)
        self.login()
        with patch.object(bridge,'invoke') as invoke:
            self.assertEqual(self.client.post('/api/shares/user').status_code,403);invoke.assert_not_called()
    def test_page_and_mutation_allowlist(self):
        self.login();self.assertEqual(self.client.get('/shares').status_code,200)
        with patch.object(bridge,'invoke',return_value=({'message':'done'},200)) as invoke:
            response=self.client.post('/api/shares/user',data=dict(csrf=self.csrf,name='alex',action='disable',revision='abc',injected='ignored'))
            self.assertEqual(response.status_code,200);self.assertNotIn('csrf',invoke.call_args.args[1]);self.assertNotIn('injected',invoke.call_args.args[1])
    def test_strict_access_and_unknown_endpoint(self):
        self.login()
        with patch.object(bridge,'invoke') as invoke:
            response=self.client.post('/api/shares/share',data=dict(csrf=self.csrf,read_only='anything',enabled='true'))
            self.assertEqual(response.status_code,400)
            self.assertEqual(self.client.post('/api/shares/arbitrary',data=dict(csrf=self.csrf)).status_code,400);invoke.assert_not_called()
    def test_helper_missing_never_invokes_sudo(self):
        with patch.object(bridge,'trusted_helper',return_value=False),patch.object(bridge.subprocess,'run') as run:
            data,status=bridge.invoke('user',dict(name='alex',password='fixture'))
            self.assertEqual(status,503);run.assert_not_called()
    def test_safe_errors_and_root_identity(self):
        self.login()
        with patch.object(bridge,'report',side_effect=backend.ShareError('Busy',409)):
            self.assertEqual(self.client.get('/api/shares').status_code,409)
        with patch.object(module.os,'getuid',return_value=0),patch.object(bridge,'report') as report:
            self.assertEqual(self.client.get('/api/shares').status_code,403);report.assert_not_called()


if __name__=='__main__':unittest.main()

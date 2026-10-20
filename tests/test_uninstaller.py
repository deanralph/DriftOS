"""Disposable filesystem tests; never run the uninstaller's systemd commands."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'deploy/uninstall.sh'
SOURCE=SCRIPT.read_text()
CODE=SOURCE.split("UNINSTALL_PY=$(cat <<'PY'\n",1)[1].split('\nPY\n)',1)[0]


class UninstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.ns={'__name__':'uninstall_fixture'};exec(compile(CODE,str(SCRIPT),'exec'),self.ns)
        self.ns['ROOT']=self.root;self.ns['OWNER']=os.getuid()
        for directory in ('opt/driftos','etc/systemd/system','etc/driftos','etc/sudoers.d','usr/local/libexec','var/lib/driftos/shares','run/driftos-installer'):
            (self.root/directory).mkdir(parents=True,exist_ok=True)
        self.app=self.root/'opt/driftos'
        (self.app/'INSTALLATION').write_text('repository=deanralph/DriftOS\ncommit='+'a'*40+'\n')
        (self.app/'app.py').write_text('fixture app')
        for name in self.ns['FILES']:
            path=self.root/name.lstrip('/');path.write_text('fixture configuration')
        (self.root/'etc/systemd/system/driftos.service').write_text('WorkingDirectory=/opt/driftos\nExecStart=/opt/driftos/.venv/bin/gunicorn app:app\n')
        self.ns['print']=lambda *args,**kwargs:None
    def run_script(self,*args):
        return subprocess.run(['bash',str(SCRIPT),*args],capture_output=True,text=True,timeout=5)
    def test_plan_help_and_invalid_arguments(self):
        for flag in ('--plan','--help'):
            result=self.run_script(flag);self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotEqual(self.run_script('--purge-everything').returncode,0)
        self.assertEqual(subprocess.run(['bash','-n',str(SCRIPT)],capture_output=True).returncode,0)
    def test_removes_application_unit_helpers_and_grants_retains_hosted_data(self):
        retained=['srv/driftos-shares/docs/example.txt','etc/samba/driftos-shares.conf','etc/exports.d/driftos.exports','var/lib/driftos/app-jobs/job.json','var/lib/driftos/shares/state.json','etc/systemd/system/driftos.service.d/custom.conf']
        for name in retained:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('keep')
        (self.root/'etc/driftos/custom.conf').write_text('keep')
        self.ns['remove']()
        self.assertFalse(self.app.exists())
        for name in self.ns['FILES']:self.assertFalse((self.root/name.lstrip('/')).exists())
        for name in retained:self.assertEqual((self.root/name).read_text(),'keep')
        self.assertTrue((self.root/'etc/driftos/custom.conf').exists())
        backups=list((self.root/'var/backups/driftos').glob('uninstall-*'));self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].stat().st_mode & 0o777,0o700)
        self.assertEqual((backups[0]/'etc/driftos/driftos.env').read_text(),'fixture configuration')
    def test_unmarked_directory_refused_without_deleting_files(self):
        (self.app/'INSTALLATION').unlink()
        with self.assertRaises(ValueError):self.ns['remove']()
        self.assertTrue((self.app/'app.py').exists());self.assertTrue((self.root/'etc/driftos/driftos.env').exists())
    def test_invalid_marker_refused(self):
        (self.app/'INSTALLATION').write_text('repository=../../outside\ncommit=anything')
        with self.assertRaises(ValueError):self.ns['preflight']()
    def test_application_symlink_and_unsafe_parent_refused(self):
        self.app.rename(self.root/'kept');self.app.symlink_to(self.root/'kept',target_is_directory=True)
        with self.assertRaises(ValueError):self.ns['remove']()
        self.assertTrue((self.root/'kept/app.py').exists())
        self.app.unlink();(self.root/'kept').rename(self.app)
        (self.root/'opt').chmod(0o777)
        with self.assertRaises(ValueError):self.ns['preflight']()
    def test_lock_symlink_refused_and_external_target_unchanged(self):
        outside=self.root/'outside';outside.write_text('keep')
        (self.root/'run/driftos-apps.lock').symlink_to(outside)
        with self.assertRaises(ValueError):self.ns['preflight']()
        self.assertEqual(outside.read_text(),'keep')
    def test_named_helper_symlink_only_link_removed(self):
        outside=self.root/'outside';outside.write_text('keep')
        helper=self.root/'usr/local/libexec/driftos-apps';helper.unlink();helper.symlink_to(outside)
        self.ns['remove']();self.assertEqual(outside.read_text(),'keep');self.assertFalse(helper.is_symlink())
    def test_custom_unit_refused(self):
        (self.root/'etc/systemd/system/driftos.service').write_text('ExecStart=/usr/bin/unrelated')
        with self.assertRaises(ValueError):self.ns['remove']()
        self.assertTrue(self.app.exists())
    def test_repeated_file_cleanup_is_safe(self):
        self.ns['remove']();self.ns['remove']();self.assertFalse(self.app.exists())
    def test_busy_package_job_prevents_service_teardown(self):
        import fcntl
        code=SOURCE.split('# BROKER_LOCKS_BEGIN\n',1)[1].split('# BROKER_LOCKS_END',1)[0]
        code=code.replace('/run/driftos-apps.lock',str(self.root/'run/driftos-apps.lock')).replace('/run/driftos-firewall.lock',str(self.root/'run/driftos-firewall.lock')).replace('/var/lib/driftos/shares',str(self.root/'var/lib/driftos/shares'))
        with (self.root/'run/driftos-apps.lock').open('a') as job:
            fcntl.flock(job,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=subprocess.run(['bash','-c','set -e; fail(){ echo "$*" >&2; exit 1; };\n'+code+'\necho service-stop-reached'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertNotIn('service-stop-reached',result.stdout)
    def service_fixture(self,fail_stop=False,state='loaded'):
        code=SOURCE.split('# SERVICE_REMOVE_BEGIN\n',1)[1].split('# SERVICE_REMOVE_END',1)[0]
        wrapper="""set -e
fail(){ echo "$*" >&2; exit 1; }
systemctl(){ if [[ $1 == show ]]; then echo "$STATE"; else echo "systemctl $*"; if [[ $1 == stop && $FAIL_STOP == 1 ]]; then return 1; fi; fi; }
python3(){ echo files-remove; }
UNINSTALL_PY=fixture
"""
        return subprocess.run(['bash','-c',wrapper+code],env=dict(os.environ,STATE=state,FAIL_STOP='1' if fail_stop else '0'),capture_output=True,text=True)
    def test_stop_failure_never_deletes_files(self):
        result=self.service_fixture(fail_stop=True)
        self.assertNotEqual(result.returncode,0);self.assertNotIn('files-remove',result.stdout)
    def test_service_stop_disable_remove_reload_order(self):
        result=self.service_fixture();self.assertEqual(result.returncode,0,result.stderr)
        self.assertLess(result.stdout.index('systemctl stop'),result.stdout.index('systemctl disable'))
        self.assertLess(result.stdout.index('systemctl disable'),result.stdout.index('files-remove'))
        self.assertLess(result.stdout.index('files-remove'),result.stdout.index('systemctl daemon-reload'))
        result=self.service_fixture(state='not-found');self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('systemctl stop',result.stdout);self.assertIn('files-remove',result.stdout)

    def test_mounted_application_subtree_refused(self):
        from unittest.mock import patch
        original=Path.read_text
        def text(path,*args,**kwargs):
            if path==Path('/proc/self/mountinfo'):return '1 2 0:3 / '+str(self.app/'data')+' rw - tmpfs tmpfs rw\n'
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',text):
            with self.assertRaises(ValueError):self.ns['remove']()
        self.assertTrue(self.app.exists())


if __name__=='__main__':unittest.main()

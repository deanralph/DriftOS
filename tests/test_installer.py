"""Offline installer checks: no root, packages, downloads or system services."""
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'deploy/install.sh'
SOURCE=SCRIPT.read_text()
ARCHIVE_CODE=SOURCE.split("<<'ARCHIVE_PY'\n",1)[1].split('\nARCHIVE_PY\n',1)[0]
REQUIRED=['app.py','requirements.txt','terminal_service.py','terminal_worker.py','templates/workspace.html','static/vendor/xterm.js']


class InstallerTests(unittest.TestCase):
    def run_script(self,*args):
        return subprocess.run(['bash',str(SCRIPT),*args],capture_output=True,text=True,timeout=5)
    def test_plan_without_root_or_network(self):
        result=self.run_script('--repo','example/DriftOS','--user','dean','--helpers','all','--sharing','both','--plan')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('firewall=1 apps=1 shares=1',result.stdout)
        self.assertIn('SMB=1 NFS=1',result.stdout)
    def test_default_plan_has_no_optional_grants(self):
        result=self.run_script('--repo','example/DriftOS','--user','dean','--plan')
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('firewall=0 apps=0 shares=0',result.stdout)
    def test_sharing_implies_only_share_helper(self):
        result=self.run_script('--repo','example/DriftOS','--user','dean','--sharing','nfs','--plan')
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('firewall=0 apps=0 shares=1',result.stdout)
    def test_rejects_bad_inputs_before_mutation(self):
        cases=[['--repo','https://github.com/owner/repo'],['--repo','owner/repo;id'],['--ref','../escape'],['--user','root'],['--user','dean\nExecStart=id'],['--helpers','anything'],['--sharing','ftp'],['--anything'],['--repo']]
        for args in cases:
            with self.subTest(args=args):
                result=self.run_script('--repo','example/DriftOS','--user','dean','--plan',*args)
                self.assertNotEqual(result.returncode,0)
                self.assertNotIn('Installing native',result.stdout)
    def test_service_render_and_shell_syntax(self):
        result=self.run_script('--print-unit','--user','dean')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('User=dean',result.stdout);self.assertIn('--workers 1 --threads 12',result.stdout)
        self.assertIn('--bind 127.0.0.1:8090',result.stdout);self.assertNotIn('NoNewPrivileges',result.stdout)
        self.assertEqual(subprocess.run(['bash','-n',str(SCRIPT)],capture_output=True).returncode,0)
    def extract(self,extra=(),omit=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name);archive=root/'source.tgz';destination=root/'output'
        with tarfile.open(archive,'w:gz') as tar:
            for path in REQUIRED:
                if path==omit:continue
                value=b'fixture'
                member=tarfile.TarInfo('repo-commit/'+path);member.size=len(value);member.mode=0o777;tar.addfile(member,io.BytesIO(value))
            for member,value in extra:tar.addfile(member,io.BytesIO(value) if value is not None else None)
        result=subprocess.run([sys.executable,'-c',ARCHIVE_CODE,str(archive),str(destination)],capture_output=True,text=True,timeout=5)
        return result,root,destination
    def file(self,path,value=b'data'):
        info=tarfile.TarInfo(path);info.size=len(value);return info,value
    def test_archive_excludes_private_and_generated_files(self):
        extra=[self.file('repo-commit/'+path) for path in ['api.json','.env','.git/config','.venv/bin/python','node_modules/thing','__pycache__/app.pyc']]
        result,_,destination=self.extract(extra)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue((destination/'app.py').is_file());self.assertFalse((destination/'api.json').exists());self.assertFalse((destination/'.git').exists())
        self.assertEqual((destination/'app.py').stat().st_mode & 0o777,0o755)
    def test_archive_traversal_and_absolute_paths_rejected(self):
        for path in ('repo-commit/../../escaped','/tmp/escaped','different-root/escaped'):
            with self.subTest(path=path):
                result,root,_=self.extract([self.file(path)])
                self.assertNotEqual(result.returncode,0);self.assertFalse((root/'escaped').exists())
    def test_archive_links_and_devices_rejected(self):
        for kind in (tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.CHRTYPE):
            member=tarfile.TarInfo('repo-commit/link');member.type=kind;member.linkname='/etc/passwd'
            result,_,_=self.extract([(member,None)])
            self.assertNotEqual(result.returncode,0)
    def test_duplicate_path_and_missing_assets_rejected(self):
        result,_,_=self.extract([self.file('repo-commit/app.py')]);self.assertNotEqual(result.returncode,0)
        result,_,_=self.extract(omit='static/vendor/xterm.js');self.assertNotEqual(result.returncode,0)
    def environment_code(self,marker,path):
        code=SOURCE.split(marker,1)[1].split("<<'PY'\n",1)[1].split('\nPY\n',1)[0]
        return code.replace("'/etc/driftos/driftos.env'",repr(str(path)))
    def test_private_environment_creation_and_preservation(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'private.env'
            create=self.environment_code('# ENV_CREATE_PY_BEGIN',path)
            result=subprocess.run([sys.executable,'-c',create,'dean'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout,'')
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            before=path.read_bytes()
            validate=self.environment_code('# ENV_VALIDATE_PY_BEGIN',path)
            result=subprocess.run([sys.executable,'-c',validate,'dean'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(path.read_bytes(),before)
            result=subprocess.run([sys.executable,'-c',validate,'someoneelse'],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertEqual(path.read_bytes(),before)
            result=subprocess.run([sys.executable,'-c',create,'dean'],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertEqual(path.read_bytes(),before)
    def test_environment_never_evaluates_shell_code(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'private.env';sentinel=Path(temp)/'should-not-exist'
            path.write_text('DRIFTOS_USER=dean\nDRIFTOS_SECRET_KEY=fixture-only\nEXAMPLE=$(touch '+str(sentinel)+')\n')
            validate=self.environment_code('# ENV_VALIDATE_PY_BEGIN',path)
            subprocess.run([sys.executable,'-c',validate,'dean'],capture_output=True,text=True)
            self.assertFalse(sentinel.exists())

    def directory_check(self,path,owner='0'):
        functions=SOURCE.split('# ADMIN_DIR_FUNCTIONS_BEGIN\n',1)[1].split('# ADMIN_DIR_FUNCTIONS_END',1)[0]
        wrapper="""set -e
fail() { printf '%s\\n' "$*" >&2; exit 1; }
stat() { if [[ $2 == '%u' ]]; then printf '%s' "$TEST_OWNER"; else command stat "$@"; fi; }
install() { local target=${!#}; mkdir -- "$target"; chmod 0755 "$target"; }
"""
        import os
        return subprocess.run(['bash','-c',wrapper+functions+'\nensure_admin_dir "$1"','fixture',str(path)],env=dict(os.environ,TEST_OWNER=owner),capture_output=True,text=True)
    def test_missing_administrative_directory_created(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'backups'
            result=self.directory_check(target)
            self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(target.is_dir())
            self.assertEqual(target.stat().st_mode & 0o777,0o755)
            target.chmod(0o700)
            self.assertEqual(self.directory_check(target).returncode,0)
            self.assertEqual(target.stat().st_mode & 0o777,0o700)
    def test_existing_unsafe_directory_not_repaired(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);target=root/'backups';target.mkdir();target.chmod(0o777)
            self.assertNotEqual(self.directory_check(target).returncode,0)
            self.assertEqual(target.stat().st_mode & 0o777,0o777)
            target.chmod(0o755)
            self.assertNotEqual(self.directory_check(target,owner='1000').returncode,0)
            link=root/'link';link.symlink_to(target,target_is_directory=True)
            self.assertNotEqual(self.directory_check(link).returncode,0)
            missing=root/'dangling';missing.symlink_to(root/'absent',target_is_directory=True)
            self.assertNotEqual(self.directory_check(missing).returncode,0)
    def test_missing_directory_under_writable_parent_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);root.chmod(0o777);target=root/'backups'
            self.assertNotEqual(self.directory_check(target).returncode,0)
            self.assertFalse(target.exists())

    def test_lan_unit_plan_and_cidr_validation(self):
        result=self.run_script('--print-unit','--user','dean','--lan')
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('--bind 0.0.0.0:8090',result.stdout)
        result=self.run_script('--repo','example/DriftOS','--user','dean','--lan','--lan-cidr','192.168.2.0/24','--plan')
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('clients: 192.168.2.0/24',result.stdout)
        for cidr in ('0.0.0.0/0','192.168.999.0/24','192.168.1.0/33','192.168.01.0/24','192.168.1.0/08','192.168.1.0/24;id','*'):
            with self.subTest(cidr=cidr):self.assertNotEqual(self.run_script('--repo','example/DriftOS','--user','dean','--lan-cidr',cidr,'--plan').returncode,0)
    def firewall_fixture(self,mode,listen='0.0.0.0',enabled='1'):
        functions=SOURCE.split('# LAN_FIREWALL_FUNCTIONS_BEGIN\n',1)[1].split('# LAN_FIREWALL_FUNCTIONS_END',1)[0]
        wrapper="""set -e
fail() { printf '%s\\n' "$*" >&2; exit 1; }
log() { printf '%s\\n' "$*" >> "$TEST_LOG"; }
ufw() { if [[ $1 == status ]]; then if [[ $MODE == ufw || $MODE == both ]]; then echo 'Status: active'; else echo 'Status: inactive'; fi; else log "ufw $*"; fi; }
systemctl() { [[ $MODE == firewalld || $MODE == both ]]; }
firewall-cmd() { case "$1" in --state) echo running;; --get-active-zones) printf 'public\\n  interfaces: eth0\\nhome\\n  interfaces: eth1\\n';; *) log "firewall-cmd $*";; esac; }
listen_address=$LISTEN
open_firewall=$ENABLED
lan_cidrs=(192.168.2.0/24)
"""
        import os
        with tempfile.TemporaryDirectory() as temp:
            log=Path(temp)/'commands'
            result=subprocess.run(['bash','-c',wrapper+functions+'\nconfigure_lan_firewall'],env=dict(os.environ,TEST_LOG=str(log),MODE=mode,LISTEN=listen,ENABLED=enabled),capture_output=True,text=True)
            return result,log.read_text() if log.exists() else ''
    def test_ufw_rule_scoped_to_requested_clients(self):
        result,commands=self.firewall_fixture('ufw')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(commands.strip(),'ufw allow from 192.168.2.0/24 to any port 8090 proto tcp comment DriftOS LAN')
    def test_firewalld_runtime_permanent_without_reload(self):
        result,commands=self.firewall_fixture('firewalld')
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(len(commands.splitlines()),4)
        self.assertIn('--zone=public --add-rich-rule=',commands);self.assertIn('--permanent --zone=home',commands)
        self.assertIn('source address="192.168.2.0/24"',commands);self.assertNotIn('--reload',commands);self.assertNotIn('--add-port',commands)
    def test_firewall_conflict_no_commands_and_optional_skip(self):
        result,commands=self.firewall_fixture('both');self.assertNotEqual(result.returncode,0);self.assertEqual(commands,'')
        for mode,listen,enabled in [('none','0.0.0.0','1'),('ufw','127.0.0.1','1'),('ufw','0.0.0.0','0')]:
            result,commands=self.firewall_fixture(mode,listen,enabled)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(commands,'')
    def test_lan_environment_clears_old_https_origin_preserves_secret(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'env';path.write_text('DRIFTOS_USER=dean\nDRIFTOS_SECRET_KEY=fixture-only\nDRIFTOS_HTTPS=1\nDRIFTOS_ORIGIN=https://example.test\n')
            code=SOURCE.split('# LAN_ENV_PY_BEGIN',1)[1].split("<<'PY_LAN_ENV'\n",1)[1].split('\nPY_LAN_ENV',1)[0].replace("'/etc/driftos/driftos.env'",repr(str(path)))
            result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('DRIFTOS_HTTPS=0',path.read_text());self.assertIn('DRIFTOS_SECRET_KEY=fixture-only',path.read_text());self.assertNotIn('DRIFTOS_ORIGIN',path.read_text());self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_archive_expansion_limit(self):
        member=tarfile.TarInfo('repo-commit/oversized');member.size=257*1024*1024
        # A header advertising an oversized member is enough; tar iteration must fail or reject it.
        with tempfile.TemporaryDirectory() as temp:
            archive=Path(temp)/'oversized.tgz'
            import gzip
            with gzip.open(archive,'wb') as out:out.write(member.tobuf());out.write(b'\0'*1024)
            result=subprocess.run([sys.executable,'-c',ARCHIVE_CODE,str(archive),str(Path(temp)/'out')],capture_output=True,timeout=5)
            self.assertNotEqual(result.returncode,0)


if __name__=='__main__':unittest.main()

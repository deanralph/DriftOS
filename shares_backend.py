#!/usr/bin/python3 -I
"""Root-owned broker for isolated DriftOS SMB/NFS shares and no-login SMB users."""
import fcntl
import grp
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile

STATE_DIR = Path('/var/lib/driftos/shares')
ROOT = Path('/srv/driftos-shares')
SMB = Path('/etc/samba/driftos-shares.conf')
NFS = Path('/etc/exports.d/driftos.exports')
MAIN = Path('/etc/samba/smb.conf')


class ShareError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def executable(name):
    return shutil.which(name, path='/usr/sbin:/usr/bin:/sbin:/bin')


def run(args, input=None, timeout=15, check=True):
    tool = executable(args[0])
    if not tool:
        raise ShareError('Required server tools are missing. Install Samba or NFS server tools through your OS package manager.', 503)
    try:
        result = subprocess.run([tool, *args[1:]], input=input, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, timeout=timeout,
                                env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ShareError('Server command could not be confirmed. Refresh status before retrying.', 503) from None
    if check and result.returncode:
        raise ShareError('Server command failed. Check the service journal and configuration. No command output or password is recorded by DriftOS.', 503)
    return result


def unit(protocol):
    choices = ('smb.service', 'smbd.service') if protocol == 'smb' else ('nfs-server.service', 'nfs-kernel-server.service')
    if not executable('systemctl'):
        return None
    for name in choices:
        result = run(['systemctl', 'show', name, '--property=LoadState', '--value'], check=False)
        if result.returncode == 0 and result.stdout.strip() == 'loaded':
            return name
    return None


def detection():
    result = {}
    for protocol, tools in (('smb', ('testparm', 'smbpasswd', 'pdbedit')), ('nfs', ('exportfs',))):
        service = unit(protocol)
        active = bool(service and run(['systemctl', 'is-active', service], check=False).stdout.strip() == 'active')
        result[protocol] = dict(installed=all(executable(t) for t in tools), service=service, active=active)
    return result


def trusted(path, directory=False):
    for item in (path, *path.parents):
        info = item.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise ShareError('Managed configuration paths must be root-owned, not symlinks, and not writable by other accounts.', 503)
    if directory and not path.is_dir():
        raise ShareError('Managed configuration directory is missing.', 503)


def load():
    trusted(STATE_DIR, True)
    file = STATE_DIR / 'state.json'
    if not file.exists():
        return dict(shares=[], users=[])
    trusted(file)
    try:
        state = json.loads(file.read_text())
        if not isinstance(state.get('shares'), list) or not isinstance(state.get('users'), list):
            raise ValueError()
        return state
    except (ValueError, AttributeError):
        raise ShareError('Managed share state is invalid. Restore a consistent configuration backup.', 503) from None


def atomic(path, content, mode=0o600):
    trusted(path.parent, True)
    if path.exists() or path.is_symlink():
        trusted(path)
    descriptor, name = tempfile.mkstemp(prefix='.driftos-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save(state):
    previous = STATE_DIR / 'state.json'
    if previous.exists():
        atomic(STATE_DIR / 'state.previous.json', previous.read_text())
    atomic(previous, json.dumps(state, sort_keys=True))


def revision(state):
    data = json.dumps(state, sort_keys=True)
    for path in (SMB, NFS, MAIN):
        data += path.read_text() if path.exists() else ''
    return hashlib.sha256(data.encode()).hexdigest()


def name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,19}', value):
        raise ShareError('Use 1–20 lowercase letters, digits, underscores or hyphens; start with a letter.')
    return value


def password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128 or any(c in value for c in ('\n','\r','\0')):
        raise ShareError('Use an SMB password of 12–128 characters without line breaks.')
    return value


def share_request(data, state):
    short = name(data.get('name'))
    protocol = data.get('protocol')
    if protocol not in ('smb', 'nfs') or type(data.get('read_only')) is not bool or type(data.get('enabled')) is not bool:
        raise ShareError('Choose SMB or NFS and valid access settings.')
    users, clients = [], []
    if protocol == 'smb':
        users = data.get('users')
        known = {u['name'] for u in state['users'] if not u.get('pending')}
        if not isinstance(users, list) or not 1 <= len(users) <= 32 or any(not isinstance(u, str) or u not in known for u in users):
            raise ShareError('Select at least one provisioned SMB share user (maximum 32).')
        users = sorted(set(users))
    else:
        raw = data.get('clients')
        if not isinstance(raw, str) or not 1 <= len(raw) <= 2048:
            raise ShareError('Enter explicit client IP addresses or CIDR networks.')
        try:
            clients = sorted(set(str(ipaddress.ip_network(c.strip(), strict=False)) for c in raw.split(',') if c.strip()))
            if not 1 <= len(clients) <= 16 or any(ipaddress.ip_network(c).prefixlen == 0 for c in clients):
                raise ValueError()
        except ValueError:
            raise ShareError('Use up to 16 comma-separated IP addresses or CIDR networks; wildcard/all-host exports are not allowed.') from None
    return dict(name=short, protocol=protocol, read_only=data['read_only'], enabled=data['enabled'], users=users, clients=clients)


def render(state):
    smb, nfs = ['# Managed by DriftOS. Edit through Shares.\n'], ['# Managed by DriftOS. Edit through Shares.\n']
    for share in state['shares']:
        if not share['enabled']:
            continue
        short = share['name']
        path = ROOT / short
        group = 'ds_s_' + short
        if share['protocol'] == 'smb':
            smb.append(f"[ds_{short}]\npath = {path}\nbrowseable = yes\nguest ok = no\nread only = {'yes' if share['read_only'] else 'no'}\nvalid users = {' '.join('ds_u_'+u for u in share['users'])}\nforce group = {group}\ncreate mask = 0660\ndirectory mask = 0770\ninherit permissions = yes\nwide links = no\nfollow symlinks = no\n\n")
        else:
            gid = grp.getgrnam(group).gr_gid
            mode = 'ro' if share['read_only'] else 'rw'
            nfs.append(str(path) + ' ' + ' '.join(f'{client}({mode},sync,subtree_check,all_squash,anonuid=65534,anongid={gid})' for client in share['clients']) + '\n')
    return ''.join(smb), ''.join(nfs)


def report(state):
    services = detection()
    for protocol in services:
        services[protocol]['ready'] = services[protocol]['installed'] and bool(services[protocol]['service'])
    # Include linking is verified by testparm's effective view rather than text matching.
    if services['smb']['ready']:
        result = run(['testparm', '-s'], check=False)
        expected = {f'ds_{s["name"]}' for s in state['shares'] if s['protocol'] == 'smb' and s['enabled']}
        actual = set(re.findall(r'^\[([^\]]+)\]', result.stdout, flags=re.M))
        linked = bool(MAIN.exists() and re.search(r'^\s*include\s*=\s*/etc/samba/driftos-shares\.conf\s*$', MAIN.read_text(), flags=re.M | re.I))
        services['smb']['linked'] = linked
        services['smb']['ready'] = result.returncode == 0 and expected <= actual and linked
    return dict(shares=state['shares'], users=state['users'], services=services, revision=revision(state), privileged=True,
                root=str(ROOT), note='SMB names use ds_; login accounts use ds_u_. NFS uses client networks and a squashed identity, not SMB passwords.')


def apply_share(data, state):
    share = share_request(data, state)
    old = next((s for s in state['shares'] if s['name'] == share['name']), None)
    if old and old['protocol'] != share['protocol']:
        raise ShareError('A share’s protocol cannot be changed. Use a different name.', 409)
    service = detection()[share['protocol']]
    if not service['installed'] or not service['service']:
        raise ShareError('Install the corresponding server tools and systemd service before adding a share.', 503)
    if share['protocol'] == 'smb':
        role = run(['testparm', '-s', '--parameter-name=server role']).stdout.strip().lower()
        backend = run(['testparm', '-s', '--parameter-name=passdb backend']).stdout.strip().lower()
        if role != 'standalone server' or backend not in ('tdbsam', 'smbpasswd'):
            raise ShareError('SMB management requires standalone Samba with a local tdbsam or smbpasswd account database.', 409)
        # Detect external names before introducing an include entry.
        sections = re.findall(r'^\[([^\]]+)\]', run(['testparm', '-s']).stdout, flags=re.M)
        if not old and 'ds_' + share['name'] in sections:
            raise ShareError('This SMB name is already defined outside DriftOS.', 409)
    trusted(ROOT, True)
    folder = ROOT / share['name']
    if share['protocol'] == 'nfs':
        external = [Path('/etc/exports'), *NFS.parent.glob('*.exports')]
        for source in external:
            if source == NFS or not source.is_file():
                continue
            for line in source.read_text().splitlines():
                fields = line.strip().split()
                if fields and fields[0].strip('"') == str(folder):
                    raise ShareError('This folder is already exported outside DriftOS. Reconcile the native definition first.', 409)
    group = 'ds_s_' + share['name']
    if not old:
        if len(state['shares']) >= 64:
            raise ShareError('The managed share limit is 64.', 409)
        if folder.exists() or folder.is_symlink():
            raise ShareError('That folder already exists. Existing directories are not adopted.', 409)
        try:
            grp.getgrnam(group)
        except KeyError:
            pass
        else:
            raise ShareError('That share group already exists. Choose another name.', 409)
        run(['groupadd', '--system', group])
        try:
            folder.mkdir(mode=0o2770)
            os.chown(folder, 0, grp.getgrnam(group).gr_gid)
            os.chmod(folder, 0o2770)
        except OSError:
            raise ShareError('Could not create the managed directory. Check for a reserved ds_s_ group before retrying.', 503) from None
    else:
        info = folder.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != grp.getgrnam(group).gr_gid or info.st_mode & 0o007:
            raise ShareError('Managed folder ownership changed. Resolve it before changing the share.', 409)
    # Retain a disabled new entry before applying so failed provisioning stays recoverable in the UI.
    if not old:
        old = dict(share, enabled=False)
        state['shares'].append(old)
        save(state)
    candidate = json.loads(json.dumps(state))
    candidate['shares'] = [share if s['name'] == share['name'] else s for s in candidate['shares']]
    smb, nfs = render(candidate)
    path = SMB if share['protocol'] == 'smb' else NFS
    content = smb if share['protocol'] == 'smb' else nfs
    previous = path.read_text() if path.exists() else ''
    previous_members = grp.getgrnam(group).gr_mem
    try:
        run(['gpasswd', '-M', ','.join('ds_u_' + u for u in share['users']), group])
        atomic(path, content, 0o644)
        if share['protocol'] == 'smb':
            effective = run(['testparm', '-s']).stdout
            if share['enabled'] and f'[ds_{share["name"]}]' not in effective:
                raise ShareError('Samba does not include the managed configuration. Complete administrator setup first.', 409)
        if service['active']:
            reload_service(share['protocol'], service['service'])
        save(candidate)
    except (ShareError, OSError):
        atomic(path, previous, 0o644)
        run(['gpasswd', '-M', ','.join(previous_members), group], check=False)
        if service['active']:
            try:
                reload_service(share['protocol'], service['service'])
            except ShareError:
                raise ShareError('Apply and rollback reload could not be confirmed. Saved definitions were restored; check native service state before retrying.', 503) from None
        raise
    return dict(message='Share saved.' + (' Active service reloaded.' if service['active'] else ' Start the service to make it available.'))


def reload_service(protocol, service):
    if protocol == 'nfs':
        run(['exportfs', '-ra'])
    else:
        run(['systemctl', 'reload', service])


def user_change(data, state):
    short = name(data.get('name'))
    action = data.get('action')
    if action not in ('create', 'password', 'enable', 'disable'):
        raise ShareError('Unsupported user action.')
    account = 'ds_u_' + short
    existing = next((u for u in state['users'] if u['name'] == short), None)
    if action == 'create' and existing:
        raise ShareError('That share user already exists.', 409)
    if action != 'create' and not existing:
        raise ShareError('Only DriftOS-managed share users can be changed.', 404)
    if not all(executable(t) for t in ('smbpasswd', 'pdbedit', 'testparm')):
        raise ShareError('Samba server tools are required for SMB user administration.', 503)
    if run(['testparm', '-s', '--parameter-name=server role']).stdout.strip().lower() != 'standalone server' or run(['testparm', '-s', '--parameter-name=passdb backend']).stdout.strip().lower() not in ('tdbsam', 'smbpasswd'):
        raise ShareError('User administration requires standalone Samba and a local account database.', 409)
    if action in ('create', 'password') and run(['testparm', '-s', '--parameter-name=unix password sync']).stdout.strip().lower() != 'no':
        raise ShareError('SMB password administration requires unix password sync = no, so Linux account passwords remain separate.', 409)
    secret = password(data.get('password')) if action in ('create', 'password') else None
    if action == 'create':
        if len(state['users']) >= 64:
            raise ShareError('The managed share-user limit is 64.', 409)
        try:
            pwd.getpwnam(account)
        except KeyError:
            pass
        else:
            raise ShareError('That Linux account already exists and will not be adopted.', 409)
        shell = executable('nologin')
        if not shell:
            raise ShareError('The nologin shell is required.', 503)
        run(['useradd', '--system', '--no-create-home', '--home-dir', '/nonexistent', '--shell', shell, '--user-group', account])
        existing = dict(name=short, account=account, enabled=False, pending=True)
        state['users'].append(existing)
        save(state)
    info = pwd.getpwnam(account)
    if info.pw_uid == 0 or info.pw_shell not in ('/usr/bin/nologin', '/sbin/nologin', '/usr/sbin/nologin', '/bin/nologin'):
        raise ShareError('Managed account identity or no-login shell changed. Resolve it before continuing.', 409)
    if secret is not None:
        # Password only enters smbpasswd stdin; it is never persisted or included in argv/output.
        run(['smbpasswd', '-s', '-a', account], input=secret + '\n' + secret + '\n')
        existing['pending'] = False
    if existing.get('pending'):
        raise ShareError('Provision this user by setting its SMB password first.', 409)
    enabled = action in ('create', 'enable') or (action == 'password' and existing['enabled'])
    run(['smbpasswd', '-e' if enabled else '-d', account])
    existing['enabled'] = enabled
    save(state)
    return dict(message='Share user updated. Existing SMB connections may need to disconnect before access changes take effect.')


def dispatch(operation, data, state):
    if operation == 'report':
        return report(state)
    if not isinstance(data.get('revision'), str) or data['revision'] != revision(state):
        raise ShareError('Share configuration changed. Refresh and review before retrying.', 409)
    if operation == 'share':
        return apply_share(data, state)
    if operation == 'user':
        return user_change(data, state)
    if operation == 'start':
        protocol = data.get('protocol')
        if protocol not in ('smb', 'nfs'):
            raise ShareError('Choose SMB or NFS.')
        services = detection()
        service = services[protocol]
        if not service['installed'] or not service['service']:
            raise ShareError('Server tools and a supported systemd service are required.', 503)
        if protocol == 'smb':
            run(['testparm', '-s'])
        run(['systemctl', 'start', service['service']], timeout=30)
        if protocol == 'nfs':
            run(['exportfs', '-ra'])
        return dict(message='Service start requested. Refresh status to confirm. Services are not enabled at boot by DriftOS.')
    raise ShareError('Unsupported share operation.')


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('report', 'share', 'user', 'start') or os.geteuid() != 0:
        raise ShareError('Use an installed root-owned helper with a supported operation.', 403)
    raw = sys.stdin.buffer.read(8193)
    if len(raw) > 8192:
        raise ShareError('Share request is too large.')
    try:
        data = json.loads(raw or b'{}')
    except ValueError:
        raise ShareError('Invalid share request.') from None
    if not isinstance(data, dict):
        raise ShareError('A request object is required.')
    trusted(STATE_DIR, True)
    with (STATE_DIR / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ShareError('Another share operation is running. Try again shortly.', 409) from None
        return dispatch(sys.argv[1], data, load())


if __name__ == '__main__':
    try:
        print(json.dumps(dict(status=200, data=main())))
    except ShareError as error:
        print(json.dumps(dict(status=error.status, error=str(error))))
    except (OSError, KeyError, ValueError, TypeError):
        print(json.dumps(dict(status=503, error='Share operation could not be confirmed. Check managed configuration and service state before retrying.')))

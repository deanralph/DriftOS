#!/usr/bin/python3 -I
"""Curated package catalogue and standalone root installation broker.

Install this complete file root-owned. No imports from the web project are used.
"""
import fcntl
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time

MANAGERS = {'apt': 'apt-get', 'dnf': 'dnf', 'yum': 'yum', 'pacman': 'pacman'}
FAMILIES = {'debian': ('apt',), 'ubuntu': ('apt',), 'fedora': ('dnf', 'yum'),
            'rhel': ('dnf', 'yum'), 'centos': ('dnf', 'yum'), 'arch': ('pacman',)}
CATALOG = {
    'btop': dict(name='btop', category='Monitoring', icon='▥', description='Interactive CPU, memory, disk and network monitor.', command='btop'),
    'htop': dict(name='htop', category='Monitoring', icon='▤', description='Interactive process viewer and process management.', command='htop'),
    'tmux': dict(name='tmux', category='Terminal', icon='⌘', description='Persistent terminal sessions and split panes.', command='tmux'),
    'rsync': dict(name='rsync', category='Files', icon='⇄', description='Efficient local and remote file synchronization.', command='rsync --help'),
    'openssh': dict(name='OpenSSH server', category='Remote access', icon='↗', description='SSH server for remote login and SFTP.', command='',
                    note='Server package: the distribution may start it automatically. No firewall rules are added.'),
    'samba': dict(name='Samba', category='File sharing', icon='▦', description='SMB server for file sharing with Windows, Linux and macOS.', command='',
                  note='Server package: the distribution may start it automatically. Shares and users need separate configuration; no firewall rules are added.'),
}
PACKAGES = {manager: {slug: slug for slug in CATALOG} for manager in MANAGERS}
for manager in ('apt', 'dnf', 'yum'):
    PACKAGES[manager]['openssh'] = 'openssh-server'
PACKAGES['pacman']['openssh'] = 'openssh'
STATE_DIR = Path('/var/lib/driftos/app-jobs')


def executable(name):
    return shutil.which(name, path='/usr/sbin:/usr/bin:/sbin:/bin')


def run(args, timeout=2):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors='replace', timeout=timeout, check=False,
                            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    return result.returncode, result.stdout[:65536].strip()


def manager_binary(manager):
    binary = executable(MANAGERS[manager])
    return binary or (executable('dnf5') if manager == 'dnf' else None)


def detect():
    try:
        release = platform.freedesktop_os_release()
    except OSError:
        release = {}
    ids = [release.get('ID', '').lower(), *release.get('ID_LIKE', '').lower().split()]
    # OS identity controls selection; a foreign package manager in PATH is insufficient.
    choices = next((FAMILIES[name] for name in ids if name in FAMILIES), ())
    available = {name: manager_binary(name) for name in MANAGERS}
    selected = next((name for name in choices if available[name]), None)
    error = None if selected else 'No supported native package manager found for this OS. Supported families: Debian/Ubuntu, Fedora/RHEL and Arch.'
    return dict(os=release.get('PRETTY_NAME', release.get('ID', 'Unknown Linux')), os_id=release.get('ID', ''),
                os_like=release.get('ID_LIKE', ''), manager=selected,
                available_managers=[name for name, binary in available.items() if binary], error=error)


def package_state(manager, package):
    try:
        if manager == 'apt':
            binary = executable('dpkg-query')
            if not binary:
                return None, None
            code, output = run([binary, '-W', '-f=${db:Status-Abbrev}\t${Version}\n', package])
            if code == 0:
                state, _, version = output.partition('\t')
                return state.strip() == 'ii', version if state.strip() == 'ii' else None
            return (False, None) if code == 1 and 'no packages found matching' in output else (None, None)
        if manager in ('dnf', 'yum'):
            binary = executable('rpm')
            if not binary:
                return None, None
            code, output = run([binary, '-q', '--qf', '%{VERSION}-%{RELEASE}\n', package])
            if code == 0:
                return True, output
            return (False, None) if code == 1 and 'is not installed' in output else (None, None)
        if manager == 'pacman':
            code, output = run([executable('pacman'), '-Q', package])
            if code == 0:
                name, _, version = output.partition(' ')
                return (True, version) if name == package else (None, None)
            return (False, None) if code == 1 and 'was not found' in output else (None, None)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None, None


def report():
    system = detect()
    manager = system['manager']
    apps = []
    for slug, item in CATALOG.items():
        package = PACKAGES[manager][slug] if manager else None
        installed, version = package_state(manager, package) if manager else (None, None)
        apps.append(dict(id=slug, package=package, installed=installed, version=version, **item))
    return dict(**system, apps=apps, sampled_at=int(time.time()))


def commands(manager, slug):
    if manager not in MANAGERS or slug not in CATALOG:
        raise ValueError('Unsupported app or package manager.')
    binary = manager_binary(manager)
    if not binary:
        raise ValueError('The selected package manager is unavailable.')
    package = PACKAGES[manager][slug]
    if manager == 'apt':
        return [[binary, 'update'], [binary, '-y', '--no-remove', 'install', '--', package]]
    if manager in ('dnf', 'yum'):
        return [[binary, '-y', 'install', '--', package]]
    # Do not run -Sy (partial upgrade) or silently upgrade the entire host with -Syu.
    return [[binary, '-S', '--needed', '--noconfirm', '--', package]]


def atomic_job(job):
    path = STATE_DIR / (job['id'] + '.json')
    temporary = STATE_DIR / (job['id'] + '.' + secrets.token_hex(4) + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(job, output)
    os.replace(temporary, path)


def process_identity(pid):
    try:
        return Path('/proc', str(pid), 'stat').read_text().rsplit(') ', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def public_job(job_id):
    if not re.fullmatch(r'[a-f0-9]{32}', job_id):
        raise ValueError('Invalid job ID.')
    path = STATE_DIR / (job_id + '.json')
    job = json.loads(path.read_text())
    # A lost worker is uncertain, never automatically failed/retried.
    if job['state'] == 'running':
        if not process_identity(job['worker_pid']) or process_identity(job['worker_pid']) != job.get('worker_start'):
            job['state'] = 'unknown'
            job['message'] = 'The installer worker ended unexpectedly. Check the native package manager and installed state before retrying.'
    elif job['state'] == 'queued' and time.time() - job['created_at'] > 30:
        job['state'] = 'unknown'
        job['message'] = 'Installer startup could not be confirmed. Refresh package status before retrying.'
    return {key: value for key, value in job.items() if key not in ('worker_pid', 'worker_start', 'package_pid')}


def recent_jobs():
    if not STATE_DIR.exists():
        return []
    paths = sorted(STATE_DIR.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
    return [public_job(path.stem) for path in paths]


def submit(slug, expected_manager):
    if slug not in CATALOG or expected_manager not in MANAGERS:
        return dict(error='Unsupported app or installer.'), 400
    selected = detect()['manager']
    if selected != expected_manager:
        return dict(error='The OS installer changed. Refresh the app library.'), 409
    installed, _ = package_state(selected, PACKAGES[selected][slug])
    if installed is None:
        return dict(error='Installed state could not be verified. Refresh before installing.'), 409
    if installed:
        return dict(error='This package is already installed. Refresh the library.'), 409
    lock = open('/run/driftos-apps.lock', 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return dict(error='Another app installation is in progress.'), 409
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Do not obscure a lost operation by immediately starting another one.
        if any(job['state'] in ('queued', 'running', 'unknown') for job in recent_jobs()):
            return dict(error='An earlier installation is still running or needs administrator review. Check its job report.'), 409
        job_id = secrets.token_hex(16)
        job = dict(id=job_id, app=slug, manager=selected, package=PACKAGES[selected][slug], state='queued',
                   created_at=int(time.time()), updated_at=int(time.time()), log='', message='Waiting for installer startup.')
        atomic_job(job)
        try:
            subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve()), 'worker', job_id, str(lock.fileno())],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True, close_fds=True, pass_fds=(lock.fileno(),),
                             env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
        except OSError:
            job.update(state='failed', message='Could not start the installer worker.')
            atomic_job(job)
            return job, 503
        return job, 202
    finally:
        lock.close()  # The detached worker retains the lock until its transaction finishes.


def redact(text):
    text = re.sub(r'(https?://)[^\s/@]+:[^\s/@]+@', r'\1<redacted>@', text)
    return re.sub(r'([?&](?:token|api_key|password|key)=)[^\s&]+', r'\1<redacted>', text, flags=re.I)


def worker(job_id, lock_fd):
    # Only the root-owned broker launches this internal command; sudoers never grants it.
    os.fstat(lock_fd)
    job = json.loads((STATE_DIR / (job_id + '.json')).read_text())
    job.update(state='running', worker_pid=os.getpid(), worker_start=process_identity(os.getpid()), message='Installing package…', updated_at=int(time.time()))
    atomic_job(job)
    tail = ''
    process = None
    try:
        if detect()['manager'] != job['manager']:
            raise ValueError('OS installer changed before installation started.')
        for command in commands(job['manager'], job['app']):
            tail = (tail + '$ ' + ' '.join(command) + '\n')[-65536:]
            env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C', 'HOME': '/root',
                   'DEBIAN_FRONTEND': 'noninteractive', 'NEEDRESTART_MODE': 'l'}
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, env=env, close_fds=True)
            job['package_pid'] = process.pid
            atomic_job(job)
            last_saved = 0
            while True:
                chunk = process.stdout.read1(4096)
                if not chunk:
                    break
                tail = (tail + chunk.decode('utf-8', errors='replace'))[-65536:]
                if time.monotonic() - last_saved >= 0.5:
                    job.update(log=redact(tail), updated_at=int(time.time()))
                    atomic_job(job)
                    last_saved = time.monotonic()
            process.stdout.close()
            if process.wait() != 0:
                raise ValueError('The native installer reported a failure. Check the log and configured repositories.')
        installed, version = package_state(job['manager'], job['package'])
        if installed is not True:
            raise ValueError('The installer exited, but package installation could not be verified. Refresh the library.')
        job.update(state='succeeded', version=version, message='Package installation verified.')
    except (OSError, ValueError) as exc:
        if process is not None and process.poll() is None:
            job.update(state='unknown', message='Output tracking failed; the native package operation may still be running. Administrator review required.')
        else:
            job.update(state='failed', message=str(exc))
    finally:
        if process is not None and process.poll() is None:
            process.wait()  # Never kill a package transaction merely because web/log tracking failed.
        job.update(log=redact(tail), updated_at=int(time.time()))
        atomic_job(job)
        os.close(lock_fd)


def secure_state():
    for path in (STATE_DIR, *STATE_DIR.parents):
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if info.st_uid != 0 or info.st_mode & 0o022 or not stat.S_ISDIR(info.st_mode):
            raise PermissionError('Untrusted app-job storage path.')


def main():
    args = sys.argv[1:]
    valid = args == ['report'] or (len(args) == 3 and args[0] == 'install' and args[1] in CATALOG and args[2] in MANAGERS) or (len(args) == 2 and args[0] == 'job' and re.fullmatch(r'[a-f0-9]{32}', args[1]))
    internal = len(args) == 3 and args[0] == 'worker' and re.fullmatch(r'[a-f0-9]{32}', args[1]) and args[2].isdigit() and int(args[2]) >= 3
    if not (valid or internal):
        print(json.dumps(dict(status=400, data=dict(error='Unsupported helper arguments.'))))
        return 1
    if os.geteuid() != 0:
        print(json.dumps(dict(status=403, data=dict(error='Administrator privileges required.'))))
        return 1
    try:
        secure_state()
        if internal:
            worker(args[1], int(args[2]))
            return 0
        if args == ['report']:
            data, status = report(), 200
            data['jobs'] = recent_jobs()
        elif args[0] == 'install':
            data, status = submit(args[1], args[2])
        else:
            data, status = public_job(args[1]), 200
    except FileNotFoundError:
        data, status = dict(error='Installation job not found.'), 404
    except (OSError, ValueError, subprocess.SubprocessError):
        data, status = dict(error='Package inspection failed. Check host package-manager access.'), 503
    print(json.dumps(dict(status=status, data=data)))
    return 0 if status in (200, 202) else 1


if __name__ == '__main__':
    raise SystemExit(main())

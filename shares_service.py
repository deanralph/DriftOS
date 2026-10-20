"""Unprivileged bridge to the root-owned share administration broker."""
import json
import os
from pathlib import Path
import pwd
import shlex
import stat
import subprocess
import shares_backend

HELPER = Path('/usr/local/libexec/driftos-shares')


def trusted_helper():
    try:
        for path in (HELPER, *HELPER.parents):
            info = path.lstat()
            if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
                return False
        return HELPER.is_file() and os.access(HELPER, os.X_OK)
    except OSError:
        return False


def invoke(operation, data=None):
    if operation not in ('report', 'share', 'user', 'start'):
        return dict(error='Unsupported share operation.'), 400
    sudo = shares_backend.executable('sudo')
    if not sudo or not trusted_helper():
        return dict(error='Administrator setup is required for share administration.'), 503
    try:
        result = subprocess.run([sudo, '-n', '--', str(HELPER), operation],
                                input=json.dumps(data or {}), stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, timeout=90,
                                env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}, check=False)
        payload = json.loads(result.stdout)
        status = payload.get('status')
        if status not in (200, 400, 403, 404, 409, 503):
            raise ValueError()
        return payload.get('data') or dict(error=payload.get('error', 'Share operation failed.')), status
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        return dict(error='Share operation could not be confirmed. Refresh and check server state before retrying.'), 503


def report():
    data, status = invoke('report')
    if status == 200:
        return data
    if trusted_helper():
        raise shares_backend.ShareError(data['error'], status)
    account = pwd.getpwuid(os.getuid()).pw_name
    installer = Path(__file__).resolve().parent / 'deploy/install-shares-helper.sh'
    return dict(privileged=False, setup_required=True, shares=[], users=[], services=shares_backend.detection(),
                root=str(shares_backend.ROOT), setup_command='sudo ' + shlex.quote(str(installer)) + ' ' + shlex.quote(account),
                note='Install the administrator helper to manage isolated SMB/NFS shares and share accounts. Existing configurations are not imported.')

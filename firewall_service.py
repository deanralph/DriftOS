"""Unprivileged bridge to the installed, root-owned firewall broker."""
import json
import os
import re
from pathlib import Path
import stat
import pwd
import shlex
import subprocess

import firewall_backend

HELPER = Path('/usr/local/libexec/driftos-firewall')


def trusted_helper():
    try:
        for path in (HELPER, *HELPER.parents):
            info = path.lstat()
            if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
                return False
        return HELPER.is_file() and os.access(HELPER, os.X_OK)
    except OSError:
        return False


def invoke(arguments):
    sudo = firewall_backend.executable('sudo')
    if not sudo or not trusted_helper():
        return None, 503
    try:
        result = subprocess.run([sudo, '-n', '--', str(HELPER), *arguments],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, timeout=40, check=False,
                                env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
        payload = json.loads(result.stdout)
        status = payload.get('status')
        if status not in (200, 400, 403, 409, 503):
            return None, 503
        return payload.get('data') or {'error': payload.get('error', 'Firewall operation failed.')}, status
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        return None, 503


def get_report():
    result, status = invoke(['report'])
    if result is not None and status == 200:
        result['privileged'] = True
        return result
    if result is not None and status == 409:
        raise RuntimeError(result.get('error', 'Firewall operation in progress.'))
    # Installation detection is still useful without administrator access.
    result = firewall_backend.report()
    result['privileged'] = False
    result['can_toggle'] = False
    result['setup_required'] = True
    account = pwd.getpwuid(os.getuid()).pw_name
    installer = Path(__file__).resolve().parent / 'deploy/install-firewall-helper.sh'
    result['setup_command'] = 'sudo ' + shlex.quote(str(installer)) + ' ' + shlex.quote(account)
    result['access_note'] = 'One-time administrator setup is required for firewall control. See Deployment → Firewall permissions.'
    return result


def change(backend, enabled, expected):
    if backend not in ('ufw', 'firewalld') or type(enabled) is not bool or not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{64}', expected):
        return {'error': 'Invalid firewall change request.'}, 400
    result, status = invoke(['set', backend, 'on' if enabled else 'off', expected])
    if result is None:
        return {'error': 'Administrator setup is required, or the firewall operation could not be confirmed. Refresh the report before retrying.'}, 503
    if status == 200:
        result['privileged'] = True
    return result, status

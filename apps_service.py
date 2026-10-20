"""Unprivileged package helper bridge. No package manager is run as root here."""
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import stat
import subprocess

import apps_backend as backend

HELPER = Path('/usr/local/libexec/driftos-apps')


def trusted_helper():
    try:
        for path in (HELPER, *HELPER.parents):
            info = path.lstat()
            if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
                return False
        return HELPER.is_file() and os.access(HELPER, os.X_OK)
    except OSError:
        return False


def invoke(args):
    sudo = backend.executable('sudo')
    if not sudo or not trusted_helper():
        return dict(error='Administrator setup is required for app installation.'), 503
    try:
        result = subprocess.run([sudo, '-n', '--', str(HELPER), *args], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, timeout=30,
                                env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
        payload = json.loads(result.stdout)
        if payload['status'] not in (200, 202, 400, 403, 404, 409, 503) or not isinstance(payload['data'], dict):
            raise ValueError('Unexpected helper response')
        return payload['data'], payload['status']
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return dict(error='The app operation could not be confirmed. Refresh the library before retrying.'), 503


def get_report():
    data, status = invoke(['report'])
    if status == 200:
        data.update(privileged=True, can_install=bool(data['manager']))
        return data
    data = backend.report()
    account = pwd.getpwuid(os.getuid()).pw_name
    installer = Path(__file__).resolve().parent / 'deploy/install-apps-helper.sh'
    data.update(privileged=False, can_install=False, jobs=[], setup_required=True,
                setup_command='sudo ' + shlex.quote(str(installer)) + ' ' + shlex.quote(account))
    return data


def install(slug, manager):
    if slug not in backend.CATALOG or manager not in backend.MANAGERS:
        return dict(error='Unsupported app or package manager.'), 400
    return invoke(['install', slug, manager])


def get_job(job_id):
    if not re.fullmatch(r'[a-f0-9]{32}', job_id):
        return dict(error='Invalid job ID.'), 400
    return invoke(['job', job_id])

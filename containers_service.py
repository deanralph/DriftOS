"""Local Docker/Podman management using fixed, unprivileged CLI commands."""
import json
import os
import pwd
import re
import shutil
import subprocess
import tempfile
import threading


class ContainerError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


operations = threading.BoundedSemaphore(2)


def command(runtime, args, timeout=12, logs=False):
    if runtime not in ('docker', 'podman'):
        raise ContainerError('Choose Docker or Podman.', 400)
    executable = shutil.which(runtime, path='/usr/bin:/usr/local/bin:/bin')
    if not executable:
        raise ContainerError(f'{runtime.title()} is not installed.', 404)
    account = pwd.getpwuid(os.getuid())
    env = dict(PATH='/usr/bin:/bin', HOME=account.pw_dir, USER=account.pw_name,
               LOGNAME=account.pw_name, LANG='C.UTF-8', XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}')
    if runtime == 'docker':
        # Never inherit remote contexts, TLS settings, registry credentials or service secrets.
        rootless = f'/run/user/{os.getuid()}/docker.sock'
        endpoint = rootless if os.path.exists(rootless) else '/var/run/docker.sock'
        prefix = [executable, '--host', f'unix://{endpoint}']
    else:
        prefix = [executable, '--remote=false']
    if not operations.acquire(blocking=False):
        raise ContainerError('Other container operations are in progress. Try again shortly.', 429)
    try:
        # Temporary output files bound memory even when a daemon emits large logs.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            try:
                result = subprocess.run(prefix + args, env=env, stdin=subprocess.DEVNULL,
                                        stdout=output, stderr=errors, timeout=timeout, check=False)
            except subprocess.TimeoutExpired:
                raise ContainerError('Runtime timed out. Refresh to check the result before retrying.', 504) from None
            except OSError:
                raise ContainerError('Unable to execute the container runtime.') from None
            if result.returncode:
                errors.seek(0)
                detail = errors.read(8192).decode('utf-8', errors='replace').lower()
                if 'permission denied' in detail:
                    raise ContainerError('Access denied to the local runtime. Configure runtime access for the DriftOS Linux account, then restart DriftOS. Docker socket access grants extensive host privileges.')
                if any(term in detail for term in ('cannot connect', 'connection refused', 'no such file or directory')):
                    raise ContainerError('Local runtime is not reachable. Start the runtime and verify its local socket, then refresh.')
                raise ContainerError('Runtime request failed. Check that the local runtime is running, your account has access, and the container still exists. No permission changes are made.')
            if logs:
                chunks = []
                for stream in (output, errors):
                    stream.seek(0, 2)
                    size = stream.tell()
                    stream.seek(max(0, size - 65536))
                    chunks.append(stream.read(65536).decode('utf-8', errors='replace'))
                return '\n'.join(chunks)[-65536:]
            output.seek(0)
            data = output.read(4 * 1024 * 1024 + 1)
            if len(data) > 4 * 1024 * 1024:
                raise ContainerError('Inventory exceeds the 4 MiB report limit.')
            return data.decode('utf-8', errors='replace')
    finally:
        operations.release()


def rows(runtime, args):
    raw = command(runtime, args + ['--format', 'json'])
    try:
        try:
            value = json.loads(raw or '[]')
            result = value if isinstance(value, list) else [value]
        except json.JSONDecodeError:
            result = [json.loads(line) for line in raw.splitlines() if line.strip()]
        if not all(isinstance(row, dict) for row in result):
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise ContainerError('The runtime returned an unsupported inventory format.') from None


def text(row, *keys):
    lower = {key.lower(): value for key, value in row.items()}
    for key in keys:
        value = lower.get(key.lower())
        if value is not None:
            if isinstance(value, list):
                return ', '.join(str(item) for item in value)[:2048]
            return str(value)[:2048]
    return '—'


def port_text(row):
    value = row.get('Ports', row.get('ports'))
    if isinstance(value, list):
        result = []
        for entry in value:
            if isinstance(entry, dict):
                host = entry.get('host_ip') or '0.0.0.0'
                result.append(f"{host}:{entry.get('host_port', '—')} → {entry.get('container_port', '—')}/{entry.get('protocol', 'tcp')}")
        return ', '.join(result) or '—'
    return text(row, 'Ports')


def inventory(runtime, kind):
    if kind == 'containers':
        data = rows(runtime, ['ps', '--all', '--no-trunc'])
        return [dict(id=text(r, 'ID', 'Id'), name=text(r, 'Names', 'Name'),
                     image=text(r, 'Image'), state=text(r, 'State'),
                     status=text(r, 'Status'), ports=port_text(r), networks=text(r, 'Networks')) for r in data]
    if kind == 'images':
        return [dict(id=text(r, 'ID', 'Id'), name=text(r, 'Repository', 'Names'),
                     tag=text(r, 'Tag'), size=text(r, 'Size'), created=text(r, 'CreatedSince', 'Created'))
                for r in rows(runtime, ['images', '--no-trunc'])]
    if kind == 'volumes':
        return [dict(name=text(r, 'Name'), driver=text(r, 'Driver'), scope=text(r, 'Scope'))
                for r in rows(runtime, ['volume', 'ls'])]
    if kind == 'networks':
        return [dict(id=text(r, 'ID', 'Id'), name=text(r, 'Name'), driver=text(r, 'Driver'), scope=text(r, 'Scope'))
                for r in rows(runtime, ['network', 'ls', '--no-trunc'])]
    raise ContainerError('Unknown inventory.', 400)


def runtimes():
    result = []
    for runtime in ('docker', 'podman'):
        installed = bool(shutil.which(runtime, path='/usr/bin:/usr/local/bin:/bin'))
        item = dict(id=runtime, installed=installed, available=False, message='Not installed')
        if installed:
            try:
                # Only ask for version, never expose full daemon info/configuration.
                version = command(runtime, ['version', '--format', '{{.Server.Version}}'])
                item.update(available=True, version=version.strip()[:100], message='Connected')
            except ContainerError as exc:
                item['message'] = str(exc)
        result.append(item)
    return result


def container_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value):
        raise ContainerError('A full container ID is required.', 400)
    return value


def action(runtime, identifier, verb):
    identifier = container_id(identifier)
    if verb not in ('start', 'stop', 'restart'):
        raise ContainerError('Unsupported container action.', 400)
    args = [verb]
    if verb in ('stop', 'restart'):
        args += ['--time', '10']
    command(runtime, args + [identifier], timeout=35)
    return dict(message=f'Container {verb} request completed.')


def logs(runtime, identifier):
    return dict(log=command(runtime, ['logs', '--tail', '200', '--timestamps', container_id(identifier)], logs=True),
                limit='Last 200 lines; output capped at 64 KiB. stdout and stderr are grouped.')

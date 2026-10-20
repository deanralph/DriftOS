"""DriftOS: Linux host overview with PAM authentication."""
import hmac
import os
import platform
import pwd
import secrets
import socket
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from functools import wraps
from urllib.parse import unquote
from werkzeug.exceptions import HTTPException

import pam
import psutil
from flask import Flask, jsonify, redirect, render_template, request, session, send_file
from flask_sock import Sock
from terminal_service import TerminalService
import firewall_service
import apps_service
import files_service
import containers_service
import shares_service
import shares_backend

app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get('DRIFTOS_SECRET_KEY') or secrets.token_hex(32),
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                  SESSION_COOKIE_SECURE=os.environ.get('DRIFTOS_HTTPS') == '1',
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=1), MAX_CONTENT_LENGTH=8192)
allowed_user = os.environ.get('DRIFTOS_USER') or pwd.getpwuid(os.getuid()).pw_name
attempts = defaultdict(deque)
attempt_lock = threading.Lock()
app.config['SOCK_SERVER_OPTIONS'] = dict(ping_interval=25, max_message_size=32768)
sock = Sock(app)
terminals = TerminalService()
login_sessions = {}
login_lock = threading.Lock()
upload_slots = threading.BoundedSemaphore(2)
app.config['FILES_ROOT'] = os.environ.get('DRIFTOS_FILES_ROOT', '/')
app.config['UPLOAD_MAX_BYTES'] = int(os.environ.get('DRIFTOS_UPLOAD_MAX_MB', '1024')) * 1024 * 1024
if not 1 <= app.config['UPLOAD_MAX_BYTES'] <= 16 * 1024 * 1024 * 1024:
    raise ValueError('DRIFTOS_UPLOAD_MAX_MB must be between 1 and 16384.')


def current_login():
    with login_lock:
        lease = login_sessions.get(session.get('login_id'))
        if lease and lease['user'] == session.get('user') == allowed_user and not lease['revoked'].is_set() and time.time() < lease['expires']:
            return lease
    return None


def revoke_login():
    with login_lock:
        old = login_sessions.pop(session.get('login_id'), None)
        if old:
            old['revoked'].set()


def authenticate(username, password):
    if username != allowed_user or username == 'root' or not password or '\x00' in password or len(password) > 1024:
        return False
    try:
        return pam.pam().authenticate(username, password, service=os.environ.get('DRIFTOS_PAM_SERVICE', 'login'))
    except (OSError, ValueError):
        return False


@app.before_request
def protect():
    if request.path == '/api/files/upload':
        request.max_content_length = app.config['UPLOAD_MAX_BYTES']
    if request.method == 'POST':
        token = request.headers.get('X-CSRF-Token', '') if request.path == '/api/files/upload' else request.form.get('csrf', '')
        if not token or not hmac.compare_digest(token.encode(), session.get('csrf', '').encode()):
            return jsonify(error='Invalid form token. Reload and try again.'), 403
    if (request.path in ('/', '/terminal', '/firewall', '/apps', '/files', '/containers', '/shares', '/logout', '/ws/terminal') or request.path.startswith('/api/')) and not current_login():
        if request.path.startswith('/api/') or request.path.startswith('/ws/'):
            return jsonify(error='Sign in required'), 401
        return redirect('/login')
    if request.path == '/ws/terminal':
        origin = os.environ.get('DRIFTOS_ORIGIN') or request.host_url.rstrip('/')
        if request.headers.get('Origin') != origin:
            return jsonify(error='Terminal origin rejected'), 403


@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    if request.path == '/terminal':
        # xterm uses generated styles and positioned cells; scripts remain self-only.
        response.headers['Content-Security-Policy'] = response.headers['Content-Security-Policy'].replace("style-src 'self'", "style-src 'self' 'unsafe-inline'")
    return response


@app.route('/login', methods=['GET', 'POST'])
def login():
    session.setdefault('csrf', secrets.token_hex(32))
    error = None
    status = 200
    if request.method == 'POST':
        now = time.monotonic()
        # One allowed account: a global bounded window avoids bypass via rotating IPs.
        with attempt_lock:
            window = attempts['login']
            while window and window[0] < now - 300:
                window.popleft()
            limited = len(window) >= 5
            if not limited:
                window.append(now)
        if limited:
            error, status = 'Too many attempts. Try again in five minutes.', 429
        elif authenticate(request.form.get('username', ''), request.form.get('password', '')):
            revoke_login()
            session.clear()
            login_id = secrets.token_hex(32)
            with login_lock:
                for key, lease in list(login_sessions.items()):
                    if lease['expires'] <= time.time():
                        lease['revoked'].set()
                        del login_sessions[key]
                login_sessions[login_id] = dict(user=allowed_user, expires=time.time() + 3600, revoked=threading.Event())
            session.update(user=allowed_user, csrf=secrets.token_hex(32), login_id=login_id)
            session.permanent = True
            return redirect('/')
        else:
            error, status = 'Unable to sign in. Check your Linux username and password.', 401
    return render_template('login.html', error=error, username=allowed_user), status


@app.post('/logout')
def logout():
    revoke_login()
    session.clear()
    return redirect('/login')


@app.get('/')
def dashboard():
    return render_template('dashboard.html', username=session['user'])


@app.get('/terminal')
def terminal_page():
    return render_template('terminal.html', username=session['user'])


def file_operation(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if os.getuid() == 0 or os.geteuid() != os.getuid() or pwd.getpwnam(session['user']).pw_uid != os.getuid():
            return jsonify(error='Files requires the signed-in non-root process account.'), 403
        try:
            return view(*args, **kwargs)
        except (files_service.FileError, OSError) as exc:
            message, status = files_service.translate_error(exc)
            return jsonify(error=message), status
        except (ValueError, UnicodeError):
            return jsonify(error='Invalid file request.'), 400
    return wrapped


def explorer():
    return files_service.Explorer(app.config['FILES_ROOT'], app.config['UPLOAD_MAX_BYTES'])


@app.errorhandler(HTTPException)
def http_error(error):
    if request.path.startswith(('/api/files', '/api/shares')):
        return jsonify(error=error.description), error.code
    return error


def container_operation(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if os.getuid() == 0 or os.geteuid() != os.getuid() or pwd.getpwnam(session['user']).pw_uid != os.getuid():
            return jsonify(error='Containers requires the signed-in non-root process account.'), 403
        try:
            return view(*args, **kwargs)
        except containers_service.ContainerError as exc:
            return jsonify(error=str(exc)), exc.status
    return wrapped


@app.get('/containers')
@container_operation
def containers_page():
    return render_template('containers.html', username=session['user'])


@app.get('/api/containers/runtimes')
@container_operation
def container_runtimes():
    return jsonify(runtimes=containers_service.runtimes())


@app.get('/api/containers/<runtime>/inventory/<kind>')
@container_operation
def container_inventory(runtime, kind):
    return jsonify(items=containers_service.inventory(runtime, kind))


@app.get('/api/containers/<runtime>/<identifier>/logs')
@container_operation
def container_logs(runtime, identifier):
    return jsonify(containers_service.logs(runtime, identifier))


@app.post('/api/containers/<runtime>/<identifier>/<verb>')
@container_operation
def container_action(runtime, identifier, verb):
    return jsonify(containers_service.action(runtime, identifier, verb))


def share_operation(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if os.getuid() == 0 or os.geteuid() != os.getuid() or pwd.getpwnam(session['user']).pw_uid != os.getuid():
            return jsonify(error='Share administration requires the signed-in non-root process account.'), 403
        try:
            return view(*args, **kwargs)
        except shares_backend.ShareError as exc:
            return jsonify(error=str(exc)), exc.status
    return wrapped


@app.get('/shares')
@share_operation
def shares_page():
    return render_template('shares.html', username=session['user'])


@app.get('/api/shares')
@share_operation
def shares_report():
    return jsonify(shares_service.report())


@app.post('/api/shares/<operation>')
@share_operation
def shares_change(operation):
    data = {key: request.form.get(key) for key in ('name', 'protocol', 'read_only', 'enabled', 'clients', 'revision', 'action', 'password') if key in request.form}
    if operation == 'share':
        for field in ('read_only', 'enabled'):
            if data.get(field) not in ('true', 'false'):
                return jsonify(error='Invalid share access settings.'), 400
            data[field] = data[field] == 'true'
        data['users'] = request.form.getlist('users')
    if operation not in ('share', 'user', 'start'):
        return jsonify(error='Unsupported share operation.'), 400
    payload, status = shares_service.invoke(operation, data)
    return jsonify(payload), status


@app.get('/files')
@file_operation
def files_page():
    return render_template('files.html', username=session['user'], initial_path=explorer().home())


@app.get('/api/files')
@file_operation
def files_list():
    return jsonify(explorer().list(request.args.get('path', '/'), request.args.get('hidden') == '1',
                                  int(request.args.get('offset', '0')), int(request.args.get('limit', '100'))))


@app.post('/api/files/folders')
@file_operation
def files_mkdir():
    return jsonify(explorer().mkdir(request.form.get('path', '/'), request.form.get('name'), request.form.get('folder_id'))), 201


@app.post('/api/files/upload')
@file_operation
def files_upload():
    if request.mimetype != 'application/octet-stream':
        return jsonify(error='Uploads require application/octet-stream.'), 415
    if not upload_slots.acquire(blocking=False):
        return jsonify(error='Other uploads are in progress. Try again after they finish.'), 429
    try:
        lease = current_login()
        authorized = lambda: lease and not lease['revoked'].is_set() and time.time() < lease['expires']
        result = explorer().upload(unquote(request.headers.get('X-Folder-Path', '/'), errors='strict'),
                                   unquote(request.headers.get('X-File-Name', ''), errors='strict'),
                                   request.headers.get('X-Folder-Id'), request.stream, authorized, request.content_length)
        return jsonify(result), 201
    finally:
        upload_slots.release()


@app.get('/api/files/download')
@file_operation
def files_download():
    stream, name, size = explorer().download(request.args.get('path', ''))
    try:
        response = send_file(stream, mimetype='application/octet-stream', as_attachment=True, download_name=name,
                             conditional=False, etag=False, max_age=0)
        response.content_length = size if size else None
        return response
    except BaseException:
        stream.close()
        raise


@app.get('/apps')
def apps_page():
    return render_template('apps.html', username=session['user'])


@app.get('/api/apps')
def apps_report():
    return jsonify(apps_service.get_report())


@app.post('/api/apps/install')
def apps_install():
    if os.geteuid() == 0 or pwd.getpwnam(session['user']).pw_uid != os.getuid():
        return jsonify(error='App installation requires the signed-in non-root process account.'), 403
    data, status = apps_service.install(request.form.get('app'), request.form.get('manager'))
    return jsonify(data), status


@app.get('/api/apps/jobs/<job_id>')
def apps_job(job_id):
    data, status = apps_service.get_job(job_id)
    return jsonify(data), status


@app.get('/firewall')
def firewall_page():
    return render_template('firewall.html', username=session['user'])


@app.get('/api/firewall')
def firewall_report():
    try:
        return jsonify(firewall_service.get_report())
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 409


@app.post('/api/firewall')
def firewall_change():
    if os.geteuid() == 0 or pwd.getpwnam(session['user']).pw_uid != os.getuid():
        return jsonify(error='Firewall control requires DriftOS to run as the signed-in non-root account.'), 403
    value = request.form.get('enabled')
    if value not in ('true', 'false'):
        return jsonify(error='enabled must be true or false'), 400
    result, status = firewall_service.change(request.form.get('backend'), value == 'true', request.form.get('revision'))
    return jsonify(result), status


@sock.route('/ws/terminal')
def terminal_socket(ws):
    lease = current_login()
    origin = os.environ.get('DRIFTOS_ORIGIN') or request.host_url.rstrip('/')
    if not lease or request.headers.get('Origin') != origin:
        ws.close(reason=1008, message='Unauthorized terminal origin or session.')
        return
    terminals.serve(ws, session['login_id'], session['user'], lease['expires'], lease['revoked'], session['csrf'])


def collect_stats():
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    drives = []
    partitions = psutil.disk_partitions(all=False)
    if not any(p.mountpoint == '/' for p in partitions):
        partitions.insert(0, type('Root', (), dict(device='root', mountpoint='/', fstype='unknown'))())
    for part in partitions:
        try:
            usage = psutil.disk_usage(part.mountpoint)
            drives.append(dict(device=part.device, mount=part.mountpoint, filesystem=part.fstype,
                               total=usage.total, used=usage.used, free=usage.free, percent=usage.percent))
        except (OSError, PermissionError):
            continue
    frequency = psutil.cpu_freq()
    return dict(hostname=socket.gethostname(), os=platform.freedesktop_os_release().get('PRETTY_NAME', platform.system()),
                kernel=platform.release(), uptime=max(0, int(time.time() - psutil.boot_time())),
                cpu=dict(percent=psutil.cpu_percent(interval=0.2), cores=psutil.cpu_count(logical=False),
                         threads=psutil.cpu_count(), frequency=round(frequency.current) if frequency else None,
                         load=list(os.getloadavg())),
                memory=dict(total=memory.total, used=memory.total-memory.available, available=memory.available,
                            percent=memory.percent, swap_used=swap.used, swap_total=swap.total),
                drives=drives, sampled_at=int(time.time()))


@app.get('/api/stats')
def stats():
    try:
        return jsonify(collect_stats())
    except (OSError, psutil.Error):
        return jsonify(error='Host metrics are temporarily unavailable'), 503


@app.get('/health')
def health():
    return jsonify(status='ok')


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8090, debug=False)

"""Bounded, per-login PTYs. No privilege escalation or retained transcripts."""
import codecs
import errno
import hmac
import fcntl
import json
import os
from pathlib import Path
import pwd
import struct
import subprocess
import sys
import termios
import threading
import time

import psutil
from simple_websocket import ConnectionClosed

MAX_TERMINALS = 4
IDLE_SECONDS = 900
MAX_INPUT = 4096


def dimensions(message):
    cols, rows = message.get('cols'), message.get('rows')
    if type(cols) is not int or type(rows) is not int or not (2 <= cols <= 500 and 2 <= rows <= 200):
        raise ValueError('Terminal size must be 2–500 columns and 2–200 rows.')
    return cols, rows


class Shell:
    def __init__(self, username, cols, rows):
        account = pwd.getpwnam(username)
        if os.getuid() == 0 or account.pw_uid != os.getuid() or os.geteuid() != os.getuid():
            raise PermissionError('Terminal requires DriftOS to run as the signed-in non-root account.')
        shell = account.pw_shell or '/bin/sh'
        if not os.path.isabs(shell) or not os.access(shell, os.X_OK):
            raise OSError('The account shell is unavailable.')
        self.master, slave = os.openpty()
        self.closed = False
        self.process = None
        try:
            self.resize(cols, rows)
            # Deliberately do not inherit API tokens, Flask secrets, agents or service environment.
            env = dict(HOME=account.pw_dir, USER=username, LOGNAME=username, SHELL=shell,
                       TERM='xterm-256color', COLORTERM='truecolor', LANG='C.UTF-8',
                       PATH='/usr/local/bin:/usr/bin:/bin')
            self.process = subprocess.Popen(
                [sys.executable, '-I', str(Path(__file__).with_name('terminal_worker.py')), shell],
                stdin=slave, stdout=slave, stderr=slave, cwd=account.pw_dir,
                env=env, start_new_session=True, close_fds=True)
            os.set_blocking(self.master, False)
        except BaseException:
            os.close(self.master)
            raise
        finally:
            os.close(slave)

    def resize(self, cols, rows):
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))

    def read(self):
        try:
            return os.read(self.master, 16384)
        except BlockingIOError:
            return None
        except OSError as exc:
            if exc.errno == errno.EIO:
                return b''
            raise

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process is not None:
            # Job-control foreground processes use their own process groups. Terminate
            # all remaining processes in this PTY's session, not just the shell group.
            targets = []
            for process in psutil.process_iter():
                try:
                    if os.getsid(process.pid) == self.process.pid:
                        targets.append(process)
                except (OSError, psutil.Error):
                    continue
            for process in targets:
                try:
                    process.terminate()
                except psutil.Error:
                    pass
            _, alive = psutil.wait_procs(targets, timeout=0.3)
            for process in alive:
                try:
                    process.kill()
                except psutil.Error:
                    pass
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
        os.close(self.master)


class TerminalService:
    def __init__(self):
        self.active = set()
        self.lock = threading.Lock()

    def serve(self, ws, login_id, username, expires, revoked, csrf):
        shell = None
        reserved = False
        reason = 'Shell exited.'
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        try:
            # Token is sent inside the socket, never in URLs/access logs.
            raw = ws.receive(timeout=5)
            message = json.loads(raw) if isinstance(raw, str) else None
            if not isinstance(message, dict) or message.get('type') != 'open':
                raise ValueError('Expected terminal open message.')
            token = message.get('csrf')
            if not isinstance(token, str) or not hmac.compare_digest(token, csrf):
                raise ValueError('Invalid terminal token. Reload and sign in again.')
            cols, rows = dimensions(message)
            with self.lock:
                if login_id in self.active:
                    raise ValueError('This login already has an open terminal. Disconnect it first.')
                if len(self.active) >= MAX_TERMINALS:
                    raise ValueError('All terminal slots are in use. Try again later.')
                if revoked.is_set() or time.time() >= expires:
                    raise ValueError('Your login session has expired. Sign in again.')
                self.active.add(login_id)
                reserved = True
            shell = Shell(username, cols, rows)
            ws.send(json.dumps(dict(type='ready')))
            last_input = time.monotonic()
            pending = b''
            while not revoked.is_set() and time.time() < expires:
                if time.monotonic() - last_input >= IDLE_SECONDS:
                    reason = 'Terminal closed after 15 minutes without keyboard input.'
                    break
                if pending:
                    try:
                        sent = os.write(shell.master, pending)
                        pending = pending[sent:]
                    except BlockingIOError:
                        pass
                data = shell.read()
                if data == b'':
                    break
                if data:
                    text = decoder.decode(data)
                    if text:
                        ws.send(json.dumps(dict(type='output', data=text)))
                raw = ws.receive(timeout=0.03)
                if raw is None:
                    continue
                if not isinstance(raw, str):
                    raise ValueError('Terminal messages must be JSON text.')
                message = json.loads(raw)
                if not isinstance(message, dict):
                    raise ValueError('Terminal message must be an object.')
                kind = message.get('type')
                if kind == 'input':
                    text = message.get('data')
                    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_INPUT:
                        raise ValueError('Terminal input is too large.')
                    if len(pending) + len(text.encode('utf-8')) > 65536:
                        raise ValueError('Terminal input buffer is full.')
                    pending += text.encode('utf-8')
                    last_input = time.monotonic()
                elif kind == 'resize':
                    shell.resize(*dimensions(message))
                elif kind == 'close':
                    reason = 'Disconnected.'
                    break
                else:
                    raise ValueError('Unsupported terminal message.')
            else:
                reason = 'Your login session ended. Sign in again.'
            ws.send(json.dumps(dict(type='exit', message=reason)))
        except ConnectionClosed:
            pass
        except (ValueError, TypeError, UnicodeError) as exc:
            try:
                ws.send(json.dumps(dict(type='error', message=str(exc))))
            except ConnectionClosed:
                pass
        except (OSError, KeyError):
            try:
                ws.send(json.dumps(dict(type='error', message='Unable to start or access the account shell. Check the server setup.')))
            except ConnectionClosed:
                pass
        finally:
            if shell:
                shell.close()
            if reserved:
                with self.lock:
                    self.active.discard(login_id)
            try:
                ws.close()
            except ConnectionClosed:
                pass

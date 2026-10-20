"""Account-level file navigation and atomic, non-overwriting streamed uploads."""
from contextlib import contextmanager
import ctypes
import errno
import hashlib
import os
from pathlib import Path
import pwd
import secrets
import stat

TEMP_PREFIX = '.driftos-upload-'
MAX_ENTRIES = 10000


class FileError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def validate_name(name):
    if not isinstance(name, str) or not name or name in ('.', '..') or '/' in name or '\\' in name or any(ord(c) < 32 or ord(c) == 127 for c in name) or name.startswith(TEMP_PREFIX):
        raise FileError('Choose a plain filename without slashes, control characters or reserved names.')
    try:
        if len(name.encode('utf-8')) > 255:
            raise FileError('The filename is too long.')
    except UnicodeError:
        raise FileError('The filename must use valid UTF-8.') from None
    return name


def parts(path):
    if not isinstance(path, str) or len(path.encode('utf-8', errors='replace')) > 4096:
        raise FileError('Invalid or excessively long folder path.')
    result = []
    for component in path.split('/'):
        if not component:
            continue
        validate_name(component)
        result.append(component)
    return result


def virtual_path(components):
    return '/' + '/'.join(components)


def folder_id(fd):
    info = os.fstat(fd)
    return hashlib.sha256(f'{info.st_dev}:{info.st_ino}'.encode()).hexdigest()


def publish(fd, temporary, name):
    """Linux atomic rename with NOREPLACE, then safe hard-link fallback."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    if rename:
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(fd, os.fsencode(temporary), fd, os.fsencode(name), 1) == 0:
            return
        code = ctypes.get_errno()
        if code not in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            raise OSError(code, os.strerror(code))
    try:
        os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        os.unlink(temporary, dir_fd=fd)
    except OSError as exc:
        if exc.errno in (errno.EOPNOTSUPP, errno.ENOSYS, errno.EPERM):
            raise FileError('This filesystem cannot publish uploads safely without overwriting. Upload is unavailable here.', 501) from None
        raise


class Explorer:
    def __init__(self, root='/', max_upload=1024 * 1024 * 1024):
        self.root = Path(root).expanduser().resolve(strict=True)
        self.max_upload = max_upload

    @contextmanager
    def directory(self, path):
        components = parts(path)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            for component in components:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            yield fd, components
        finally:
            os.close(fd)

    def home(self):
        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        try:
            return virtual_path(home.relative_to(self.root).parts)
        except ValueError:
            return '/'

    def list(self, path, hidden=False, offset=0, limit=100):
        if not (0 <= offset <= MAX_ENTRIES and 1 <= limit <= 250):
            raise FileError('Invalid page range.')
        with self.directory(path) as (fd, components):
            entries, skipped, truncated = [], 0, False
            with os.scandir(fd) as scan:
                for entry in scan:
                    if entry.name.startswith(TEMP_PREFIX) or (not hidden and entry.name.startswith('.')):
                        continue
                    if len(entries) >= MAX_ENTRIES:
                        truncated = True
                        break
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        skipped += 1
                        continue
                    kind = 'folder' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) else 'link' if stat.S_ISLNK(info.st_mode) else 'special'
                    entries.append(dict(name=entry.name, path=virtual_path([*components, entry.name]), type=kind,
                                        size=info.st_size if kind == 'file' else None, modified=info.st_mtime,
                                        permissions=stat.filemode(info.st_mode)))
            entries.sort(key=lambda item: (item['type'] != 'folder', item['name'].casefold(), item['name']))
            if offset >= len(entries):
                offset = max(0, ((len(entries) - 1) // limit) * limit)
            writable = os.access('.', os.W_OK | os.X_OK, dir_fd=fd, effective_ids=True)
            return dict(path=virtual_path(components), actual_path=str(self.root.joinpath(*components)),
                        root=str(self.root), home=self.home(), parent=virtual_path(components[:-1]) if components else None,
                        folder_id=folder_id(fd), writable=writable, entries=entries[offset:offset + limit],
                        total=len(entries), offset=offset, limit=limit, truncated=truncated, skipped=skipped,
                        next_offset=offset + limit if offset + limit < len(entries) else None,
                        max_upload_bytes=self.max_upload)

    def check_target(self, fd, expected):
        if not expected or expected != folder_id(fd):
            raise FileError('The destination folder changed. Refresh it before uploading or creating folders.', 409)

    def upload(self, path, name, expected, stream, authorized=lambda: True, length=None):
        validate_name(name)
        if length is not None and length > self.max_upload:
            raise FileError('This file exceeds the configured upload limit.', 413)
        with self.directory(path) as (fd, components):
            self.check_target(fd, expected)
            temporary = TEMP_PREFIX + secrets.token_hex(16) + '.part'
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=fd)
            total = 0
            try:
                with os.fdopen(descriptor, 'wb') as output:
                    while True:
                        if not authorized():
                            raise FileError('Your login session ended. Sign in again.', 401)
                        chunk = stream.read(65536)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > self.max_upload:
                            raise FileError('This file exceeds the configured upload limit.', 413)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if length is not None and total != length:
                    raise FileError('The upload was incomplete. No file was published.', 400)
                if not authorized():
                    raise FileError('Your login session ended. Sign in again.', 401)
                publish(fd, temporary, name)
                try:
                    os.fsync(fd)
                except OSError:
                    raise FileError('The file may already be present, but folder sync could not be confirmed. Refresh before retrying.', 503) from None
                return dict(name=name, path=virtual_path([*components, name]), size=total)
            finally:
                try:
                    os.unlink(temporary, dir_fd=fd)
                except FileNotFoundError:
                    pass

    def mkdir(self, path, name, expected):
        validate_name(name)
        with self.directory(path) as (fd, components):
            self.check_target(fd, expected)
            os.mkdir(name, mode=0o750, dir_fd=fd)
            return dict(name=name, path=virtual_path([*components, name]))

    def download(self, path):
        components = parts(path)
        if not components:
            raise FileError('Choose a regular file to download.')
        with self.directory(virtual_path(components[:-1])) as (fd, _):
            result = os.open(components[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
        try:
            info = os.fstat(result)
            if not stat.S_ISREG(info.st_mode):
                raise FileError('Only regular files can be downloaded.')
            return os.fdopen(result, 'rb'), components[-1], info.st_size
        except BaseException:
            os.close(result)
            raise


def translate_error(exc):
    if isinstance(exc, FileError):
        return str(exc), exc.status
    if exc.errno in (errno.EACCES, errno.EPERM, errno.ELOOP):
        return 'Access denied. Check account permissions; symbolic links are not followed.', 403
    if exc.errno == errno.ENOENT:
        return 'The file or folder no longer exists. Refresh this folder.', 404
    if exc.errno == errno.EEXIST:
        return 'That name already exists. Nothing was overwritten.', 409
    if exc.errno in (errno.ENOSPC, errno.EDQUOT):
        return 'The destination has insufficient space or quota.', 507
    if exc.errno == errno.EROFS:
        return 'This filesystem is read-only.', 403
    if exc.errno in (errno.ENOTDIR, errno.EISDIR, errno.ENAMETOOLONG, errno.EINVAL):
        return 'Invalid file or folder path. Symbolic-link folders are not followed.', 400
    return 'The file operation could not be confirmed. Refresh the folder before retrying.', 503

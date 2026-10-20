#!/usr/bin/env bash
# Remove the native DriftOS application/service; retain packages and hosted data.
set -Eeuo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077
accept=0 plan=0
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
while (($#)); do
  case "$1" in
    --yes) accept=1;; --plan) plan=1;;
    --help|-h)
      printf '%s\n' 'Usage: sudo bash uninstall.sh [--yes | --plan]' 'Removes driftos.service, /opt/driftos, private app configuration, helper scripts' 'and their sudoers grants. Keeps OS packages, shares/users, runtime state, backups' 'and firewall rules. --plan makes no host changes. No custom install paths.'
      exit 0;;
    *) fail "Unknown option: $1";;
  esac
  shift
done
cat <<'PLAN'
DriftOS uninstall plan
  Stop/disable driftos.service (active logins and terminals end).
  Remove /etc/systemd/system/driftos.service and /opt/driftos (including .venv).
  Remove /etc/driftos/driftos.env; remove its directory only when empty.
  Remove driftos-{apps,firewall,shares} helper files and their sudoers grants.
  Back up removed unit/private config/helpers/grants under /var/backups/driftos.
  KEEP package-manager packages, share data/definitions/users/groups, native
  services, app-job/share state, installer backups, firewall rules and custom
  systemd drop-ins. Installer coordination locks remain until reboot.
  Refuse active package/helper operations, mounted app subtrees and unmarked
  application folders. No package manager, user deletion or firewall command runs.
PLAN
if (( plan )); then exit 0; fi
[[ $EUID == 0 ]] || fail 'Run with sudo; use --plan for a read-only preview.'
[[ -d /run/systemd/system ]] || fail 'This uninstaller requires systemd.'
for tool in python3 flock systemctl; do command -v "$tool" >/dev/null || fail "Missing prerequisite: $tool"; done
if (( ! accept )); then
  [[ -r /dev/tty ]] || fail 'No terminal. Review --plan and supply --yes.'
  read -r -p 'Remove DriftOS using this plan? [y/N] ' answer </dev/tty
  [[ $answer == y || $answer == Y ]] || fail 'Uninstall cancelled.'
fi
# Root-only coordination shared with the installer. Never unlink a held lock.
for path in /run /run/driftos-installer; do
  if [[ ! -e $path && ! -L $path ]]; then install -d -o root -g root -m 0700 "$path"; fi
  [[ -d $path && ! -L $path && $(stat -c '%u' "$path") == 0 ]] || fail "Unsafe lock directory: $path"
  mode=$(stat -c '%a' "$path")
  (( (8#$mode & 0022) == 0 )) || fail "Writable lock directory: $path"
done
# UNINSTALL_PY_BEGIN
UNINSTALL_PY=$(cat <<'PY'
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile

ROOT=Path('/')
OWNER=0

def target(value):
    return ROOT/value.lstrip('/')

def present(path):
    return path.exists() or path.is_symlink()

def directory(path):
    if not present(path):
        raise ValueError('Missing administrative parent: '+str(path))
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=OWNER or info.st_mode & 0o022:
        raise ValueError('Unsafe administrative directory: '+str(path))

def parents(path):
    current=path.parent
    while True:
        directory(current)
        if current==ROOT:break
        if ROOT not in current.parents:raise ValueError('Path is outside administrative root.')
        current=current.parent

def administrative_file(path):
    if not present(path):return
    parents(path)
    info=path.lstat()
    # Named symlinks are unlinked as links, never followed or copied by value.
    if info.st_uid!=OWNER or not (stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)):
        raise ValueError('Unsafe administrative file: '+str(path))
    if stat.S_ISREG(info.st_mode) and info.st_mode & 0o022:
        raise ValueError('Writable administrative file: '+str(path))

FILES=['/etc/systemd/system/driftos.service','/etc/driftos/driftos.env']
for name in ('apps','firewall','shares'):
    FILES+=['/etc/sudoers.d/driftos-'+name,'/usr/local/libexec/driftos-'+name]
LOCKS=['/run/driftos-installer/lock','/run/driftos-apps.lock','/run/driftos-firewall.lock','/var/lib/driftos/shares/lock']

def application():
    app=target('/opt/driftos')
    if not present(app):return
    parents(app);directory(app)
    marker=app/'INSTALLATION'
    administrative_file(marker)
    if not marker.is_file() or marker.is_symlink():
        raise ValueError('Unmarked /opt/driftos folder: refusing recursive deletion. Review/migrate the manual installation first.')
    values=dict(line.split('=',1) for line in marker.read_text().splitlines() if '=' in line)
    if not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+',values.get('repository','')) or not re.fullmatch(r'[a-f0-9]{40}',values.get('commit','')):
        raise ValueError('Invalid DriftOS installation marker: refusing application deletion.')
    if not shutil.rmtree.avoids_symlink_attacks:
        raise ValueError('This Python lacks safe recursive directory removal.')
    mountinfo=Path('/proc/self/mountinfo').read_text()
    mounts=[line.split()[4] for line in mountinfo.splitlines()]
    for raw in mounts:
        decoded=re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),raw)
        mount=Path(decoded)
        if mount==app or app in mount.parents:
            raise ValueError('Mounted filesystem at/under application folder; unmount it before uninstalling.')

def preflight():
    application()
    for name in FILES:administrative_file(target(name))
    for name in LOCKS:
        path=target(name)
        administrative_file(path)
        if path.is_symlink():raise ValueError('Unsafe symlink lock: '+str(path))
    config=target('/etc/driftos')
    if present(config):directory(config);parents(config)
    shares=target('/var/lib/driftos/shares')
    if present(shares):directory(shares);parents(shares)
    unit=target(FILES[0])
    if unit.is_symlink() and os.readlink(unit)!='/dev/null':raise ValueError('Custom linked service requires manual review.')
    if unit.is_file() and not unit.is_symlink():
        text=unit.read_text()
        if 'WorkingDirectory=/opt/driftos' not in text or 'ExecStart=/opt/driftos/.venv/bin/gunicorn ' not in text:
            raise ValueError('The named service is not the installer-managed DriftOS unit. Review it manually.')
    base=target('/var/backups/driftos')
    current=base
    while not present(current):current=current.parent
    directory(current);parents(current) if current!=ROOT else None
    if present(base):directory(base);parents(base)

def remove():
    preflight()
    base=target('/var/backups/driftos')
    base.mkdir(parents=True,exist_ok=True,mode=0o700)
    backup=Path(tempfile.mkdtemp(prefix='uninstall-',dir=base))
    backup.chmod(0o700)
    for name in FILES:
        path=target(name)
        if not present(path):continue
        destination=backup/name.lstrip('/')
        destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if path.is_symlink():destination.symlink_to(os.readlink(path))
        else:shutil.copy2(path,destination,follow_symlinks=False)
    # Revoke fixed sudo grants first. No native package/user/share configuration is removed.
    for name in FILES:
        if name.startswith('/etc/sudoers.d/'):
            target(name).unlink(missing_ok=True)
    app=target('/opt/driftos')
    if present(app):shutil.rmtree(app)
    for name in FILES:
        target(name).unlink(missing_ok=True)
    config=target('/etc/driftos')
    if config.is_dir() and not config.is_symlink():
        try:config.rmdir()
        except OSError:pass  # Preserve unrelated/custom files.
    (backup/'REMOVED.json').write_text(json.dumps({'target_paths':FILES+['/opt/driftos'],'retained':'Packages, hosted data, accounts, native share configs, state, firewall rules, drop-ins and older backups.'},indent=2))
    print('DriftOS application cleanup complete. Private recovery backup: '+str(backup))

if __name__=='__main__':
    try:
        if sys.argv[1]=='preflight':preflight()
        elif sys.argv[1]=='remove':remove()
        else:raise ValueError('Invalid uninstall phase.')
    except (OSError,ValueError) as error:
        print('Uninstall error: '+str(error),file=sys.stderr)
        sys.exit(1)
PY
)
# UNINSTALL_PY_END
python3 -c "$UNINSTALL_PY" preflight
exec 9>/run/driftos-installer/lock
flock -n 9 || fail 'Another installer/uninstaller is running.'
# BROKER_LOCKS_BEGIN
# Hold native broker locks before stopping the service: never interrupt an app package job.
exec 8>/run/driftos-apps.lock
flock -n 8 || fail 'A package installation is running. Let it finish, then retry.'
exec 7>/run/driftos-firewall.lock
flock -n 7 || fail 'A firewall operation is running. Retry after it completes.'
if [[ -d /var/lib/driftos/shares ]]; then
  exec 6>/var/lib/driftos/shares/lock
  flock -n 6 || fail 'A share operation is running. Retry after it completes.'
fi
# BROKER_LOCKS_END
python3 -c "$UNINSTALL_PY" preflight
# SERVICE_REMOVE_BEGIN
if ! load_state=$(systemctl show driftos.service --property=LoadState --value); then
  [[ $load_state == not-found ]] || fail 'Could not establish service state; refusing file removal.'
fi
if [[ $load_state != not-found ]]; then
  systemctl stop driftos.service
  if ! systemctl disable driftos.service; then
    [[ $load_state == masked ]] || fail 'Could not disable DriftOS; files have not been removed.'
  fi
fi
python3 -c "$UNINSTALL_PY" remove
systemctl daemon-reload
systemctl reset-failed driftos.service 2>/dev/null || true
# SERVICE_REMOVE_END
printf '%s\n' 'DriftOS uninstalled. OS packages, shared data/accounts/configuration, native' 'services, runtime metadata, firewall rules and backups have been retained.' 'Review existing port 8090 rules separately; earlier installers did not record' 'whether an identical rule existed before installation. No firewall rules were removed.'

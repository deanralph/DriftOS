#!/usr/bin/env bash
# Public GitHub -> native systemd deployment. Review a pinned revision before running.
set -Eeuo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 022

usage() {
  cat <<'HELP'
Usage: sudo bash install.sh --repo OWNER/REPO [options]
  --user USER             Existing non-root Linux account (default: sudo caller)
  --ref REF              GitHub branch, tag or commit (default: main)
  --helpers LIST         firewall,apps,shares; all; or none (default: none)
  --sharing LIST         smb,nfs; both; or none (default: none; implies shares helper)
  --yes                  Accept the printed installation plan without a prompt
  --plan                 Print the plan only; no root, download or host changes
  --print-unit           Print the generated systemd unit only
  --help                 Show this help

Public repositories only. Supports apt-based Debian/Ubuntu and dnf/yum-based
Fedora/RHEL families with systemd. Installs /opt/driftos and driftos.service.
Uses a local browser through an SSH tunnel; no public listener, proxy, TLS,
firewall changes or Docker/Podman installation are configured.
--sharing smb appends the managed Samba include and unix password sync = no;
existing Samba must be standalone with a local tdbsam/smbpasswd database.
Native package scripts may start services. Updates stop DriftOS temporarily.
HELP
}
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
repo='' revision='main' account=${SUDO_USER:-} helpers='none' sharing='none' accept=0 plan=0 print_unit=0
while (($#)); do
  case "$1" in
    --repo|--ref|--user|--helpers|--sharing)
      (($# >= 2)) && [[ -n $2 && $2 != --* ]] || fail "Missing value for $1"
      case "$1" in
        --repo) repo=$2;; --ref) revision=$2;; --user) account=$2;;
        --helpers) helpers=$2;; --sharing) sharing=$2;;
      esac
      shift 2;;
    --yes) accept=1; shift;; --plan) plan=1; shift;; --print-unit) print_unit=1; shift;;
    --help|-h) usage; exit 0;; *) fail "Unknown option: $1";;
  esac
done
[[ $account =~ ^[a-z_][a-z0-9_-]{0,30}$ && $account != root ]] || fail 'Specify an existing non-root --user, for example --user dean.'
if (( ! print_unit )); then
  [[ $repo =~ ^[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9._-]*$ && $repo != *.git && $repo != */. && $repo != */.. ]] || fail '--repo must be OWNER/REPO, without a URL, token or .git suffix.'
fi
[[ $revision =~ ^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$ && $revision != *..* && $revision != */ ]] || fail 'Invalid GitHub ref.'
want_firewall=0 want_apps=0 want_shares=0 want_smb=0 want_nfs=0
case "$helpers" in
  all) want_firewall=1; want_apps=1; want_shares=1;;
  none) :;;
  *) IFS=',' read -ra helper_items <<< "$helpers"
     for item in "${helper_items[@]}"; do
       case "$item" in firewall) want_firewall=1;; apps) want_apps=1;; shares) want_shares=1;; *) fail 'Invalid --helpers list.';; esac
     done;;
esac
case "$sharing" in
  both|smb,nfs|nfs,smb) want_smb=1; want_nfs=1; want_shares=1;;
  smb) want_smb=1; want_shares=1;; nfs) want_nfs=1; want_shares=1;; none) :;;
  *) fail 'Use --sharing smb, nfs, smb,nfs, both or none.';;
esac
if (( want_firewall || want_apps || want_shares )); then
  [[ $account =~ ^[a-z][a-z0-9_-]*$ ]] || fail 'Helper installers require an account starting with a lowercase letter.'
fi

write_unit() {
  cat <<UNIT
[Unit]
Description=DriftOS server management
After=network.target

[Service]
Type=exec
User=$account
WorkingDirectory=/opt/driftos
EnvironmentFile=/etc/driftos/driftos.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/driftos/.venv/bin/gunicorn --worker-class gthread --workers 1 --threads 12 --timeout 120 --bind 127.0.0.1:8090 --access-logfile - --error-logfile - app:app
Restart=on-failure
RestartSec=5
TimeoutStopSec=45

[Install]
WantedBy=multi-user.target
UNIT
}
if (( print_unit )); then write_unit; exit 0; fi
cat <<PLAN
DriftOS installation plan
  Repository: $repo @ $revision (resolved to a commit before download)
  Account: $account (existing account; its Linux password is used for login)
  Application: /opt/driftos; service: driftos.service
  Listener: 127.0.0.1:8090; one worker, twelve threads
  Admin helpers: firewall=$want_firewall apps=$want_apps shares=$want_shares
  Sharing packages: SMB=$want_smb NFS=$want_nfs
  Existing application/unit/config backed up under /var/backups/driftos.
  Existing private environment and session signing key preserved.
  Package installation can run native setup scripts and start services.
  SMB setup, when selected, adds its include and disables Unix password sync.
  Skipped optional flags do not revoke or update previously installed helpers.
  No firewall rules, reverse proxy, TLS or Docker/Podman access changes.
PLAN
if (( plan )); then exit 0; fi
[[ $EUID == 0 ]] || fail 'Run with sudo; use --plan for a read-only preview.'
[[ -d /run/systemd/system ]] || fail 'This installer requires a server booted with systemd.'
id "$account" >/dev/null 2>&1 || fail 'The selected Linux account does not exist. Create it and set its password first.'
[[ $(id -u "$account") != 0 ]] || fail 'Root cannot run DriftOS.'
account_shell=$(getent passwd "$account" | cut -d: -f7)
account_home=$(getent passwd "$account" | cut -d: -f6)
[[ -x $account_shell && $account_shell != */nologin && $account_shell != */false ]] || fail 'The selected account requires an executable interactive shell.'
# shellcheck source=/dev/null
. /etc/os-release
os_family=" ${ID:-} ${ID_LIKE:-} "
case "$os_family" in
  *' debian '*|*' ubuntu '*) manager=apt;;
  *' fedora '*|*' rhel '*|*' centos '*)
    if command -v dnf >/dev/null; then manager=dnf
    elif command -v dnf5 >/dev/null; then manager=dnf5
    elif command -v yum >/dev/null; then manager=yum
    else fail 'No native dnf/dnf5/yum found.'; fi;;
  *) fail 'Automatic installation supports Debian/Ubuntu and Fedora/RHEL families. Use the manual deployment guide on other systems.';;
esac
if (( ! accept )); then
  [[ -r /dev/tty ]] || fail 'No terminal available. Review --plan, then supply --yes.'
  read -r -p 'Install using this plan? [y/N] ' answer </dev/tty
  [[ $answer == y || $answer == Y ]] || fail 'Installation cancelled.'
fi
existing_dropins=$(systemctl show driftos.service --property=DropInPaths --value 2>/dev/null || true)
[[ -z $existing_dropins ]] || fail 'Existing systemd drop-ins could override the deployment. Review and migrate them before using this installer.'

# ADMIN_DIR_FUNCTIONS_BEGIN
check_admin_dir() {
  local path=$1 mode
  [[ -d $path && ! -L $path && $(stat -c '%u' "$path") == 0 ]] || fail "Unsafe administrative directory: $path"
  mode=$(stat -c '%a' "$path")
  (( (8#$mode & 0022) == 0 )) || fail "Writable administrative directory: $path"
}
ensure_admin_dir() {
  local path=$1
  if [[ ! -e $path && ! -L $path ]]; then
    check_admin_dir "$(dirname -- "$path")"
    install -d -o root -g root -m 0755 "$path"
  fi
  check_admin_dir "$path"
}
# ADMIN_DIR_FUNCTIONS_END
# Minimal server images may omit /var/backups or other standard directories.
# Validate each parent before creation; never repair unsafe existing paths silently.
check_admin_dir /
for path in /opt /etc /etc/systemd /etc/systemd/system /var /var/backups /run; do
  ensure_admin_dir "$path"
done

if [[ -e /run/driftos-installer || -L /run/driftos-installer ]]; then
  [[ -d /run/driftos-installer && ! -L /run/driftos-installer && $(stat -c '%u' /run/driftos-installer) == 0 ]] || fail 'Unsafe installer lock directory.'
  lock_mode=$(stat -c '%a' /run/driftos-installer)
  (( (8#$lock_mode & 0022) == 0 )) || fail 'Unsafe installer lock permissions.'
fi
install -d -m 0700 /run/driftos-installer
command -v flock >/dev/null || fail 'Install util-linux (flock) before running this installer.'
exec 9>/run/driftos-installer/lock
flock -n 9 || fail 'Another DriftOS installer is running.'
printf '\nInstalling native prerequisites…\n'
if [[ $manager == apt ]]; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip python3-dev build-essential libpam0g sudo curl ca-certificates util-linux passwd
else
  "$manager" -y install python3 python3-pip python3-devel gcc pam sudo curl ca-certificates util-linux shadow-utils
fi
python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit('Python 3.10+ is required; provision a newer supported server OS/Python before installing DriftOS.')
PY
python3 - <<'PY'
import stat
from pathlib import Path
paths=['/opt/driftos','/etc/driftos','/etc/driftos/driftos.env','/etc/systemd/system/driftos.service','/var/backups/driftos']
for raw in paths:
    p=Path(raw)
    if p.exists() or p.is_symlink():
        info=p.lstat()
        if info.st_uid!=0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise SystemExit('Unsafe existing install destination: '+raw+'. Migrate it to root-owned source first.')
PY
install -d -o root -g root -m 0700 /var/backups/driftos /etc/driftos
backup=$(mktemp -d /var/backups/driftos/install-XXXXXXXX)
staging=$(mktemp -d /opt/.driftos-install-XXXXXXXX)
chmod 0755 "$staging"
committed=0 swapped=0 transaction=0 prior_active=0 prior_enabled=0
[[ ! -e /etc/systemd/system/driftos.service ]] || cp -a /etc/systemd/system/driftos.service "$backup/driftos.service"
[[ ! -e /etc/driftos/driftos.env ]] || cp -a /etc/driftos/driftos.env "$backup/driftos.env"
systemctl is-active --quiet driftos.service && prior_active=1
systemctl is-enabled --quiet driftos.service && prior_enabled=1
cleanup() {
  local result=$?
  trap - EXIT INT TERM
  set +e
  if (( result != 0 )); then
    printf '\nInstallation failed. Backup: %s\n' "$backup" >&2
    if (( transaction && ! committed )); then
      printf 'Attempting application/unit/environment rollback; native packages are retained.\n' >&2
      rollback_ok=1
      systemctl stop driftos.service >/dev/null 2>&1 || true
      systemctl disable driftos.service >/dev/null 2>&1 || true
      if (( swapped )); then
        if [[ -d /opt/driftos ]]; then mv /opt/driftos "$backup/failed-application" || rollback_ok=0; fi
        if [[ -d $backup/application ]] && (( rollback_ok )); then mv "$backup/application" /opt/driftos || rollback_ok=0; fi
      fi
      if [[ -f $backup/driftos.service ]]; then cp -a "$backup/driftos.service" /etc/systemd/system/driftos.service || rollback_ok=0
      else systemctl disable driftos.service >/dev/null 2>&1 || true; rm -f /etc/systemd/system/driftos.service; fi
      if [[ -f $backup/driftos.env ]]; then cp -a "$backup/driftos.env" /etc/driftos/driftos.env || rollback_ok=0
      else rm -f /etc/driftos/driftos.env; fi
      systemctl daemon-reload || rollback_ok=0
      if (( prior_enabled )); then systemctl enable driftos.service || true
      else systemctl disable driftos.service >/dev/null 2>&1 || true; fi
      if (( ! rollback_ok )); then printf 'Rollback file restoration failed; service left stopped. Recover from the backup manually.\n' >&2; fi
      if (( prior_active && rollback_ok )); then systemctl start driftos.service || printf 'Rollback restart failed; inspect journalctl -u driftos.\n' >&2; fi
    elif (( committed )); then
      printf 'The core app passed health checks and remains installed. Optional setup may be partial; inspect the error before retrying.\n' >&2
    fi
  fi
  [[ ! -d $staging ]] || rm -rf -- "$staging"
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

encoded_ref=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$revision")
printf '\nResolving public GitHub revision…\n'
if [[ $revision =~ ^[a-fA-F0-9]{40}$ ]]; then
  commit=${revision,,}
else
  curl --fail --silent --show-error --proto '=https' --connect-timeout 15 --max-time 60 \
    -H 'Accept: application/vnd.github+json' "https://api.github.com/repos/$repo/commits/$encoded_ref" -o "$staging/commit.json"
  commit=$(python3 -c 'import json,re,sys;sha=json.load(open(sys.argv[1])).get("sha","");assert re.fullmatch("[a-f0-9]{40}",sha),"Invalid GitHub commit response";print(sha)' "$staging/commit.json")
fi
printf 'Downloading commit %s…\n' "$commit"
curl --fail --silent --show-error --proto '=https' --connect-timeout 15 --max-time 180 --max-filesize 52428800 \
  "https://codeload.github.com/$repo/tar.gz/$commit" -o "$staging/source.tar.gz"
# ARCHIVE_PY_BEGIN -- isolated validation/extraction, exercised by tests/test_installer.py
python3 - "$staging/source.tar.gz" "$staging/source" <<'ARCHIVE_PY'
import os
from pathlib import Path, PurePosixPath
import sys
import tarfile

archive, destination = Path(sys.argv[1]), Path(sys.argv[2])
skip={'.git','.venv','node_modules','__pycache__','.env','api.json'}
with tarfile.open(archive, 'r:gz') as tar:
    members=[]
    total=0
    for member in tar:
        total+=member.size
        if len(members)>=20000 or total>256*1024*1024:
            raise SystemExit('Repository archive exceeds installation limits.')
        members.append(member)
    if not members:raise SystemExit('Empty repository archive.')
    top=None
    seen=set()
    for member in members:
        path=PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in member.name:
            raise SystemExit('Unsafe repository archive path.')
        if not member.isfile() and not member.isdir():
            raise SystemExit('Repository symlinks, hardlinks and special files are not accepted.')
        if top is None:top=path.parts[0]
        if path.parts[0]!=top:raise SystemExit('Expected one repository archive root.')
        relative=Path(*path.parts[1:])
        if not path.parts[1:] or any(part in skip for part in relative.parts):continue
        if relative in seen:raise SystemExit('Duplicate repository archive path.')
        seen.add(relative)
    destination.mkdir(mode=0o755)
    for member in members:
        parts=PurePosixPath(member.name).parts[1:]
        if not parts or any(part in skip for part in parts):continue
        target=destination.joinpath(*parts)
        if member.isdir():target.mkdir(parents=True,exist_ok=True,mode=0o755)
        else:
            target.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
            with tar.extractfile(member) as source, target.open('xb') as output:
                while chunk:=source.read(1024*1024):output.write(chunk)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
required=['app.py','requirements.txt','terminal_service.py','terminal_worker.py','templates/workspace.html','static/vendor/xterm.js']
if any(not (destination/name).is_file() for name in required):
    raise SystemExit('Archive is missing required DriftOS source/assets.')
ARCHIVE_PY
# ARCHIVE_PY_END

# Preserve existing configuration, but never source it as shell code.
# ENV_VALIDATE_PY_BEGIN
python3 - "$account" <<'PY'
import os
from pathlib import Path
import secrets
import shlex
import sys
path=Path('/etc/driftos/driftos.env')
if path.exists():
    values={}
    for line in path.read_text().splitlines():
        tokens=shlex.split(line,comments=True)
        if not tokens:continue
        if len(tokens)!=1 or '=' not in tokens[0]:raise SystemExit('Existing environment has unsupported syntax; review it before installing.')
        key,value=tokens[0].split('=',1);values[key]=value
    if values.get('DRIFTOS_USER')!=sys.argv[1] or not values.get('DRIFTOS_SECRET_KEY'):
        raise SystemExit('Existing environment user/key does not match. Review the private file before installing.')
    path.chmod(0o600)
PY
# Existing processes on port 8090 must not be mistaken for this service.
if (( ! prior_active )); then
  python3 - <<'PY'
import socket
with socket.socket() as probe:
    try:probe.bind(('127.0.0.1',8090))
    except OSError:raise SystemExit('Port 8090 is occupied. Stop the conflicting service before installing.')
PY
fi
[[ ! -d /opt/driftos ]] || cp -a /opt/driftos "$backup/application"
transaction=1
systemctl stop driftos.service 2>/dev/null || { (( ! prior_active )) || fail 'Could not stop existing DriftOS.'; }
swapped=1
if [[ -d /opt/driftos ]]; then rm -rf -- /opt/driftos; fi
mv "$staging/source" /opt/driftos
# Build at the final path: virtualenv executable shebangs are not relocatable.
install -d -o "$account" -g "$(id -gn "$account")" -m 0755 /opt/driftos/.venv
runuser -u "$account" -- env -i HOME="$account_home" USER="$account" LOGNAME="$account" PATH=/usr/bin:/bin LC_ALL=C.UTF-8 /bin/sh -c 'cd /opt/driftos && exec python3 -m venv .venv'
runuser -u "$account" -- env -i HOME="$account_home" USER="$account" LOGNAME="$account" PATH=/usr/bin:/bin LC_ALL=C.UTF-8 /bin/sh -c 'cd /opt/driftos && exec .venv/bin/python -m pip install --no-input -r requirements.txt'
if [[ ! -f /etc/driftos/driftos.env ]]; then
  # ENV_CREATE_PY_BEGIN
  python3 - "$account" <<'PY'
import os,secrets,sys
fd=os.open('/etc/driftos/driftos.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as out:
    out.write('DRIFTOS_USER='+sys.argv[1]+'\nDRIFTOS_PAM_SERVICE=login\nDRIFTOS_HTTPS=0\nDRIFTOS_FILES_ROOT=/\nDRIFTOS_UPLOAD_MAX_MB=1024\nDRIFTOS_SECRET_KEY='+secrets.token_hex(32)+'\n')
PY
fi
write_unit > /etc/systemd/system/driftos.service
chmod 0644 /etc/systemd/system/driftos.service
printf '%s\n' "repository=$repo" "requested_ref=$revision" "commit=$commit" > /opt/driftos/INSTALLATION
systemctl daemon-reload
systemctl enable driftos.service
systemctl start driftos.service
healthy=0
for attempt in {1..20}; do
  if systemctl is-active --quiet driftos.service && curl --fail --silent --max-time 2 http://127.0.0.1:8090/health | python3 -c 'import json,sys;sys.exit(0 if json.load(sys.stdin).get("status")=="ok" else 1)' 2>/dev/null; then healthy=1; break; fi
  sleep 1
done
(( healthy )) || fail 'HTTP health check failed. Inspect journalctl -u driftos.service.'
committed=1

# Optional permissions/packages are deliberately outside core-app rollback.
if (( want_firewall )); then bash /opt/driftos/deploy/install-firewall-helper.sh "$account"; fi
if (( want_apps )); then bash /opt/driftos/deploy/install-apps-helper.sh "$account"; fi
if (( want_shares )); then bash /opt/driftos/deploy/install-shares-helper.sh "$account"; fi
sharing_packages=()
if [[ $manager == apt ]]; then
  (( ! want_smb )) || sharing_packages+=(samba)
  (( ! want_nfs )) || sharing_packages+=(nfs-kernel-server)
  if ((${#sharing_packages[@]})); then DEBIAN_FRONTEND=noninteractive apt-get install -y "${sharing_packages[@]}"; fi
else
  (( ! want_smb )) || sharing_packages+=(samba samba-common-tools)
  (( ! want_nfs )) || sharing_packages+=(nfs-utils)
  if ((${#sharing_packages[@]})); then "$manager" -y install "${sharing_packages[@]}"; fi
fi
if (( want_smb )); then
  python3 - "$backup" <<'PY'
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
path=Path('/etc/samba/smb.conf')
for item in (path,*path.parents):
    if item.exists() or item.is_symlink():
        info=item.lstat()
        if info.st_uid!=0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):raise SystemExit('Unsafe Samba configuration path.')
previous=path.read_bytes() if path.exists() else None
if previous is not None:
    shutil.copy2(path,Path(sys.argv[1])/'smb.conf')
    for parameter,allowed in [('server role',{'standalone server'}),('passdb backend',{'tdbsam','smbpasswd'})]:
        result=subprocess.run(['testparm','-s','--parameter-name='+parameter],capture_output=True,text=True)
        if result.returncode or result.stdout.strip().lower() not in allowed:raise SystemExit('Existing Samba is not a supported standalone/local configuration. Configure it manually.')
text=(previous.decode() if previous is not None else '[global]\n    server role = standalone server\n    security = user\n    passdb backend = tdbsam\n    map to guest = Never\n')
addition='\n# DriftOS managed configuration\n[global]\n    unix password sync = no\n    include = /etc/samba/driftos-shares.conf\n'
if not text.endswith(addition):text+=addition
try:
    path.write_text(text);path.chmod(0o644)
    checked=subprocess.run(['testparm','-s'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if checked.returncode:raise RuntimeError()
except (OSError,RuntimeError):
    if previous is None:path.unlink(missing_ok=True)
    else:path.write_bytes(previous)
    raise SystemExit('Samba validation failed; previous main configuration restored. Core DriftOS remains installed.')
PY
fi
cat <<FINISH

DriftOS is installed and enabled at boot.
  Service: sudo systemctl status driftos --no-pager
  Logs:    sudo journalctl -u driftos -f
  Commit:  $commit
  Backup:  $backup

From YOUR COMPUTER (replace SERVER_IP):
  ssh -N -L 18090:127.0.0.1:8090 $account@SERVER_IP
Then open http://127.0.0.1:18090 and use $account's SERVER Linux password.
Health checks do not verify real PAM login, terminals or client share access.
Sharing daemons were not explicitly started/reloaded/enabled; package scripts
may have started them. Review Shares, native configs and firewall policy.
For direct network access, configure HTTPS/reverse proxy and DRIFTOS_ORIGIN
using the deployment guide. Do not expose the loopback HTTP listener publicly.
FINISH

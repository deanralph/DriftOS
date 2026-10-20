#!/bin/sh
# One-time administrator setup; does not install server packages, start services or open ports.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
if [ "$(id -u)" -ne 0 ] || [ "$#" -ne 1 ]; then
  echo 'Usage: sudo install-shares-helper.sh <DriftOS Linux account>' >&2; exit 1
fi
DRIFTOS_ACCOUNT=$1
case "$DRIFTOS_ACCOUNT" in
 ''|root|*[!a-z0-9_-]*|[0-9-]*) echo 'Use a non-root Linux account name.' >&2; exit 1;;
esac
[ "$(id -u "$DRIFTOS_ACCOUNT")" -ne 0 ]
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TEMP_RULE=$(mktemp)
trap 'rm -f "$TEMP_RULE"' EXIT HUP INT TERM
cat > "$TEMP_RULE" <<EOF
# DriftOS manages only isolated share definitions, ds_u_ accounts and ds_s_ groups.
$DRIFTOS_ACCOUNT ALL=(root) NOPASSWD: /usr/local/libexec/driftos-shares report, /usr/local/libexec/driftos-shares share, /usr/local/libexec/driftos-shares user, /usr/local/libexec/driftos-shares start
EOF
visudo -cf "$TEMP_RULE"
# Refuse unsafe existing destination paths before installation.
python3 - <<'PY'
import os, stat
from pathlib import Path
paths=['/usr/local/libexec','/var/lib/driftos/shares','/srv/driftos-shares','/etc/samba','/etc/exports.d','/etc/samba/driftos-shares.conf','/etc/exports.d/driftos.exports','/usr/local/libexec/driftos-shares','/etc/sudoers.d/driftos-shares']
for raw in paths:
 p=Path(raw)
 for item in (p,*p.parents):
  if not item.exists() and not item.is_symlink(): continue
  info=item.lstat()
  if info.st_uid!=0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
   raise SystemExit('Unsafe administrator destination: '+str(item))
PY
install -d -o root -g root -m 0755 /usr/local/libexec /srv/driftos-shares /etc/samba /etc/exports.d
install -d -o root -g root -m 0700 /var/lib/driftos/shares
if [ ! -e /etc/samba/driftos-shares.conf ]; then
 printf '%s\n' '# Managed by DriftOS.' > /etc/samba/driftos-shares.conf
 chmod 0644 /etc/samba/driftos-shares.conf
fi
if [ ! -e /etc/exports.d/driftos.exports ]; then
 printf '%s\n' '# Managed by DriftOS.' > /etc/exports.d/driftos.exports
 chmod 0644 /etc/exports.d/driftos.exports
fi
install -o root -g root -m 0755 "$SOURCE_DIR/shares_backend.py" /usr/local/libexec/driftos-shares
install -o root -g root -m 0440 "$TEMP_RULE" /etc/sudoers.d/driftos-shares
printf '%s\n' 'Installed share helper. No packages installed, services started, ports opened or existing smb.conf/exports entries changed.'
printf '%s\n' 'For SMB, install standalone Samba and add the following at the END of /etc/samba/smb.conf, after backing it up:' '[global]' '    include = /etc/samba/driftos-shares.conf' 'Validate with: testparm -s'
printf '%s\n' 'NFS uses /etc/exports.d/driftos.exports. Install the native NFS server separately. Share folders stay within /srv/driftos-shares.'

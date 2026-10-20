#!/bin/sh
# One-time administrator setup. Does not install apps or start services.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
if [ "$(id -u)" -ne 0 ]; then
  echo 'Run this installer as an administrator.' >&2
  exit 1
fi
if [ "$#" -ne 1 ]; then
  echo 'Usage: install-apps-helper.sh <DriftOS Linux user>' >&2
  exit 1
fi
DRIFTOS_ACCOUNT=$1
case "$DRIFTOS_ACCOUNT" in
  ''|root|*[!a-z0-9_-]*|[0-9-]*) echo 'Use a non-root Linux account name containing lowercase letters, digits, underscores or hyphens.' >&2; exit 1 ;;
esac
if [ "$(id -u "$DRIFTOS_ACCOUNT")" -eq 0 ]; then
  echo 'The DriftOS account must have a non-root UID.' >&2
  exit 1
fi
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TEMP_RULE=$(mktemp)
trap 'rm -f "$TEMP_RULE"' EXIT HUP INT TERM
# Only catalogue installation/reporting is granted; the internal worker is not.
cat > "$TEMP_RULE" <<EOF
# DriftOS: curated package reports, fixed app IDs and job reads only.
$DRIFTOS_ACCOUNT ALL=(root) NOPASSWD: /usr/local/libexec/driftos-apps report, /usr/local/libexec/driftos-apps install *, /usr/local/libexec/driftos-apps job *
EOF
visudo -cf "$TEMP_RULE"
install -d -o root -g root -m 0755 /usr/local/libexec
install -d -o root -g root -m 0700 /var/lib/driftos /var/lib/driftos/app-jobs
install -o root -g root -m 0755 "$SOURCE_DIR/apps_backend.py" /usr/local/libexec/driftos-apps
install -o root -g root -m 0440 "$TEMP_RULE" /etc/sudoers.d/driftos-apps
printf '%s\n' 'Installed app-library helper. No apps were installed and no services were started.'

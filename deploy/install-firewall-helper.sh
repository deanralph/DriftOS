#!/bin/sh
# One-time administrator installation. Does not enable/disable the firewall.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
if [ "$(id -u)" -ne 0 ]; then
  echo 'Run this installer as an administrator.' >&2
  exit 1
fi
if [ "$#" -ne 1 ]; then
  echo 'Usage: install-firewall-helper.sh <DriftOS Linux user>' >&2
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
# The helper accepts only these fixed operations and a validated state hash.
cat > "$TEMP_RULE" <<EOF
# DriftOS: firewall reports and UFW/firewalld enable/disable only.
$DRIFTOS_ACCOUNT ALL=(root) NOPASSWD: /usr/local/libexec/driftos-firewall report, /usr/local/libexec/driftos-firewall set ufw on *, /usr/local/libexec/driftos-firewall set ufw off *, /usr/local/libexec/driftos-firewall set firewalld on *, /usr/local/libexec/driftos-firewall set firewalld off *
EOF
visudo -cf "$TEMP_RULE"
install -d -o root -g root -m 0755 /usr/local/libexec
install -o root -g root -m 0755 "$SOURCE_DIR/firewall_backend.py" /usr/local/libexec/driftos-firewall
install -o root -g root -m 0440 "$TEMP_RULE" /etc/sudoers.d/driftos-firewall
printf '%s\n' 'Installed firewall report/control helper. Firewall state and rules were not changed.'

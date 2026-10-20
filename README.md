# DriftOS

A Linux server overview built with the DriftStream UI v0.2.0 shared stylesheet and style guide. Live CPU, RAM, uptime and mounted-drive capacity behind Linux PAM sign-in, plus an interactive browser terminal using xterm.js and Linux PTYs. A firewall manager detects UFW/firewalld/nftables/iptables, reports rules/status and supports UFW/firewalld on/off control after administrator setup. A curated app library detects the native apt/dnf/yum/pacman installer and offers six tools with installed status and background installation jobs after separate administrator setup.

## Local start

Run as the Linux account you want to sign in as (not root):

```bash
cd /home/dean/Projects/DriftOS
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Open http://127.0.0.1:8090 and enter that account’s Linux username and password. PAM policy must permit password authentication for the running account. No separate DriftOS password is created or stored. Actual password authentication requires validation on your target host.

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
node --check static/terminal.js
node --check static/firewall.js
node --check static/apps.js
node --check static/files.js
```

See [deployment](docs/wiki/deployment.md), [API](docs/wiki/api.md) and [verification](docs/wiki/verification.md). Keep the development server on loopback; configure HTTPS and a stable session key before remote deployment.

## Terminal

After signing in, choose **Terminal → Connect terminal**. The shell runs in your home directory as the same non-root account running DriftOS. It supports ANSI output, interactive commands, resizing, Ctrl+C/Ctrl+D, disconnect and starting a new shell. Disconnect/sign-out ends the shell; displayed output remains until a new terminal/navigation. One terminal per login, four globally, 15 minutes without keyboard input and an absolute one-hour login limit. Restart requires signing in again.

Commands have normal account permissions and can modify the server; shell history may persist. Service environment secrets are not inherited, but the shell can access any files the account normally can. Deliberately detached processes/services may outlive disconnect. See [usage](docs/wiki/usage.md) and [deployment](docs/wiki/deployment.md), including `DRIFTOS_ORIGIN` and WebSocket proxy setup. Use one Gunicorn worker with twelve threads.

Browser terminal assets and licenses are included in `static/vendor/`. To regenerate: `npm ci --ignore-scripts --no-audit --no-fund` then `npm run vendor`. Node/npm is not required at runtime.

For documentation publication, read remote pages first using `python3 scripts/publish_docs.py --snapshot-dir /tmp/driftos-wiki-baseline`, reconcile their contents into local Markdown, then publish using `--baseline-dir /tmp/driftos-wiki-baseline`. The publisher refuses changed remote content and verifies each successful write.

## Firewall manager

Choose **Firewall** for installed tools, status, policies, rule entries and the full report. The on/off switch uses existing UFW/firewalld configuration. Raw nftables/iptables is read-only. Unknown status means live inspection could not be verified.

A one-time administrator setup is required on the host; review the standalone helper and installer, then run:

```bash
sudo /home/dean/Projects/DriftOS/deploy/install-firewall-helper.sh dean
```

This installs a root-owned isolated-Python helper and narrow sudoers grant for the named account. It does not change firewall rules/state. Run DriftOS as the same non-root account. After installation, Refresh the firewall page. See [deployment](docs/wiki/deployment.md) for privileges, precise command semantics, removal and recovery limitations. Host installation/live switching remain pending; development tests use mocked firewall changes.

## App library

Applications lists btop, htop, tmux, rsync, OpenSSH server and Samba. It selects apt-get for Debian/Ubuntu, dnf/dnf5 then yum for Fedora/RHEL, or pacman for Arch (including Omarchy), and queries the native package database. Other OS families are currently unsupported.

Review and run once as administrator, then Refresh Applications:

```bash
sudo /home/dean/Projects/DriftOS/deploy/install-apps-helper.sh dean
```

Setup installs only the root-owned curated-package helper/authorization and private job directory; it does not install apps. Individual installs run as persistent background jobs with progress/logs and final package verification. Package scripts may start SSH/Samba services automatically; shares, firewall configuration, uninstall and service switches are separate. Pacman uses existing metadata without a full host upgrade. See Deployment, Usage and Data & recovery for exact commands, privileges and failed/unknown-job recovery.

The helper has not been installed and no live package transaction was run during development; installation tests are mocked. Read-only Omarchy/pacman discovery is verified.

## File explorer

**Files** opens in your Linux home and can browse account-readable folders. Open a destination and drop desktop files onto the file list; uploads start automatically with per-file progress. Upload files also selects multiple files. Existing names are never overwritten. New folders, hidden-file visibility, filtering, pagination and regular-file downloads are available; symbolic links are not followed. Directory drops and overwrite/delete/rename/move are not implemented.

No sudo setup is required. Default filesystem root is `/`; set `DRIFTOS_FILES_ROOT` to an existing narrower directory if desired. `DRIFTOS_UPLOAD_MAX_MB` defaults to 1024 (1 GiB) per file. Uploads use account permissions and mode 0600; completed files persist in the selected host directory. See Deployment and Data & recovery for proxy limits, partial-file cleanup and publication guarantees. Menu item numbering was removed.

## Containers

Open **Containers** to manage existing local Docker/Podman workloads. The page detects installed and accessible runtimes, lists containers/images/volumes/networks, filters inventories, displays logs and confirms start/stop/restart actions. Native account access is required; DriftOS never runs sudo or changes socket permissions. Docker prefers `/run/user/<uid>/docker.sock` when present and otherwise `/var/run/docker.sock`; Podman uses local non-root account storage. Docker daemon access grants extensive host privileges. This release does not create/delete containers, pull images, deploy Compose stacks or connect to remote engines. See [usage](docs/wiki/usage.md) and [deployment](docs/wiki/deployment.md).

## SMB / NFS shares

**Shares** adds/edits isolated folders under `/srv/driftos-shares`, selects SMB users or NFS IP/CIDR clients, sets read-only/write access and enables/disables definitions without deleting data. Share users receive `ds_u_` no-login system accounts and separate SMB passwords; their enabled state and password can be managed here. Existing system/domain users and external shares are not imported. NFS uses squashed client identities and network access rules, not SMB passwords.

One-time administrator setup (review first; substitute the actual DriftOS Linux account):

```bash
sudo ./deploy/install-shares-helper.sh dean
```

The installer grants only the reviewed broker operations. It does not install server packages, modify the main Samba configuration, start/enable services or open firewall ports. Install native server tools separately, link and validate the managed Samba include, and follow [Deployment](docs/wiki/deployment.md) before using the service-start control. See [Usage](docs/wiki/usage.md) for the add-share/user workflows and [Data and recovery](docs/wiki/data-and-recovery.md) for state, retained data and recovery limitations. Real server/client integration is pending host provisioning.

## Install as a server service

`deploy/install.sh` installs from a public GitHub repo on Ubuntu/Debian or Fedora/RHEL-family systemd servers. Select an existing non-root Linux account with a valid password. Preview locally:

```bash
bash deploy/install.sh --repo OWNER/REPO --user dean --helpers all --sharing both --plan
```

The source repository is [deanralph/DriftOS](https://github.com/deanralph/DriftOS). Replace `dean` with the existing server account in this download-and-run command. Use a reviewed commit SHA instead of `main` to pin the bootstrap and application revision:

```bash
( set -e; repo="deanralph/DriftOS"; ref="main"; installer=$(mktemp); trap 'rm -f "$installer"' EXIT; curl -fsS --proto '=https' --connect-timeout 15 --max-time 60 "https://raw.githubusercontent.com/$repo/$ref/deploy/install.sh" -o "$installer"; sudo bash "$installer" --repo "$repo" --ref "$ref" --user dean --helpers all --sharing both --lan --yes )
```

The example explicitly enables all three admin helpers, Samba/NFS package setup and direct LAN HTTP access on port 8090. Core-only installs omit `--helpers all --sharing both`. The installer creates `/opt/driftos`, a private persistent environment, and an enabled systemd/Gunicorn service. With `--lan`, open `http://SERVER_LAN_IP:8090`; the service binds all IPv4 interfaces, resets HTTPS-cookie/origin settings for direct HTTP, and adds source-scoped rules to active UFW/firewalld. Default client ranges are 10.0.0.0/8, 172.16.0.0/12 and 192.168.0.0/16; repeat `--lan-cidr` to override them, or `--no-firewall` to skip rules. Without `--lan`, use the printed SSH tunnel command. HTTP is unencrypted, so use a trusted LAN. HTTPS/reverse proxy and Docker/Podman provisioning remain separate. Optional package scripts may start sharing services; SMB setup appends the managed include and disables Unix password synchronization after backup/validation. Skipped helper flags do not revoke/update existing grants.

Application/unit/config backups are private under `/var/backups/driftos`; core failure attempts rollback, while native packages and optional setup are retained. Actual privileged installation/rollback has not been executed here; see [Deployment](docs/wiki/deployment.md), [Recovery](docs/wiki/data-and-recovery.md) and [Verification](docs/wiki/verification.md).

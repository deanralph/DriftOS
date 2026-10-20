# Deployment & configuration

## Local development

Run as the intended non-root Linux user. libpam and `/etc/pam.d/login` must exist. Install Python 3 and its venv/pip support through the host package manager.

```bash
cd /home/dean/Projects/DriftOS
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Visit `http://127.0.0.1:8090`. Stop with Ctrl+C. No system services, firewall rules or PAM configuration are installed by this project.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DRIFTOS_USER` | Process owner's username | Only allowed account; root always denied |
| `DRIFTOS_PAM_SERVICE` | `login` | Existing host PAM policy |
| `DRIFTOS_SECRET_KEY` | Random per process start | Session signing secret; provision stable high-entropy value for deployment |
| `DRIFTOS_HTTPS` | unset | Set `1` behind HTTPS to require secure session cookies |
| `DRIFTOS_ORIGIN` | Request scheme + host | Exact browser origin (for example `https://server.example`), no trailing slash; set behind a TLS reverse proxy |

For normal use run under the same account being authenticated. Another account may fail host PAM/shadow permissions; do not run the web application as root to work around this. Interactive MFA/password-change conversations are not implemented. Validate host policy before relying on access.

## Persistent deployment

Provision a secret key through a private environment file or service secret, excluded from Git. Generate one using `python3 -c 'import secrets; print(secrets.token_hex(32))'` in a private local terminal. Supply it as `DRIFTOS_SECRET_KEY` without committing it. After setting the environment, run:

```bash
cd /home/dean/Projects/DriftOS
.venv/bin/gunicorn --workers 1 --threads 12 --bind 127.0.0.1:8090 app:app
```

One worker is required: attempt throttling, login revocation and terminal connection slots are process-local. Each open WebSocket occupies a request thread; twelve threads leave room for HTTP requests alongside the four terminal slots. Use a trusted HTTPS reverse proxy for network access, set `DRIFTOS_HTTPS=1`, and retain the loopback application binding. The automated installer below generates a systemd unit; real server deployment is unverified. No reverse proxy, TLS certificate or Docker/Compose setup is supplied or verified. Do not expose plain HTTP login on a network. Flask's built-in server is development only.

Health command: `curl --fail http://127.0.0.1:8090/health` expects `{"status":"ok"}`. This proves HTTP routing, not PAM authentication. Update by stopping, backing up source/configuration, installing requirements and restarting. Roll back source and dependencies together; sessions invalidate if signing key changes.

## Terminal prerequisites and proxy behavior

The service must run as the same non-root Linux UID being authenticated. The terminal refuses root, mismatched real/effective UIDs and another account's UID. It uses host PTYs (`/dev/ptmx` / `/dev/pts`), the user's configured executable shell and home directory. Do not grant sudo or run DriftOS as root to enable the terminal. This is a normal account shell, not a sandbox; it can read and modify everything that account can access.

For HTTPS proxy deployment, set `DRIFTOS_ORIGIN` to the exact browser origin, retain the browser Origin header, and proxy `/ws/terminal` with HTTP/1.1 WebSocket Upgrade/Connection support. Set the proxy's read timeout above the 25-second ping interval (e.g. 90 seconds). Use `wss://` for network terminal traffic; the frontend selects it automatically under HTTPS. Proxy/TLS configuration has not been deployed or validated here. A wrong/missing Origin is rejected with HTTP 403 before shell creation.

Vendored browser assets are included. To regenerate them with Node/npm installed:

```bash
cd /home/dean/Projects/DriftOS
npm ci --ignore-scripts --no-audit --no-fund
npm run vendor
```

For terminal tests install `.venv/bin/pip install -r requirements-dev.txt` instead of only runtime requirements. Stop/restart the service after Python/template updates; existing logins and shells end and users must sign in again. Old cookies from pre-terminal versions lack a live server-side login lease and must sign in again. Terminal sessions cannot reconnect to an old shell; New terminal starts fresh.

## Firewall permissions

Requirements: a supported firewall already installed, `sudo`/`visudo`, system Python 3 and a normal same-UID DriftOS account. firewalld switching additionally requires systemd. DriftOS does not install a firewall or modify its rule configuration. It stays unprivileged; do not run the app as root.

After reviewing `firewall_backend.py` and the installer, an administrator must run the following on the host (the account below is the verified local development account):

```bash
cd /home/dean/Projects/DriftOS
sudo ./deploy/install-firewall-helper.sh dean
```

The installer requires an administrator password on this host. It creates/updates `/usr/local/libexec/driftos-firewall` (root:root 0755) and `/etc/sudoers.d/driftos-firewall` (root:root 0440), validating the sudoers fragment with `visudo -cf` first. The authorization grants that account only the helper's report and validated UFW/firewalld enable/disable operations. The helper rejects extra arguments and shell injection. No firewall state or rules are changed by installation. These files are persistent host configuration outside the repository and must be updated by rerunning the installer after helper-source changes.

Then refresh the Firewall page; no app restart is required for helper discovery. A read-only integration check is:

```bash
sudo -n -- /usr/local/libexec/driftos-firewall report
```

Expected: a JSON envelope with `status: 200` and a `data` report. Output may contain private network rules; do not publish actual host reports to documentation. The installer and privileged host integration remain unexecuted/unverified here. The page still detects installed tools without the helper, but cannot enable switching without verified privileged access.

Enabling UFW uses existing persistent UFW configuration (`ufw --force enable`); disabling uses `ufw --force disable` and UFW changes its boot configuration normally. firewalld uses `systemctl start/stop firewalld.service`, which changes runtime service state and does not alter its boot-enabled setting. Disabling firewalld requires normal cleanup-on-exit behavior. Existing rules may block the browser/SSH connection when enabled. Perform first live acceptance from a local console or with an independent recovery path. Installation alone does not exercise that risk.

To revoke DriftOS firewall management, remove only the installed sudoers fragment and helper as an administrator (this does not modify firewall state):

```bash
sudo rm -- /etc/sudoers.d/driftos-firewall /usr/local/libexec/driftos-firewall
```

Refresh the Firewall page to confirm control is unavailable. Back up prior helper/sudoers versions privately before upgrades if they need to be recoverable. Do not grant blanket passwordless access to `ufw`, `nft`, `iptables`, `systemctl`, Python or the writable repository file.

## App-library administrator setup

Prerequisites: a supported native OS/package manager, readable package database, configured trusted repositories, working package signatures/network and system Python 3. Debian/Ubuntu needs apt-get/dpkg-query; Fedora/RHEL needs dnf or dnf5 (yum fallback) and rpm; Arch needs pacman. Repository availability varies: for example a curated package can be absent from enabled enterprise repositories. DriftOS does not add repositories, bootstrap missing package managers, import keys or bypass package signatures.

After reviewing `apps_backend.py` and the installer, run once as an administrator for the account that runs DriftOS:

```bash
cd /home/dean/Projects/DriftOS
sudo ./deploy/install-apps-helper.sh dean
```

This creates/updates `/usr/local/libexec/driftos-apps` (root:root 0755), `/etc/sudoers.d/driftos-apps` (root:root 0440), and `/var/lib/driftos/app-jobs` with private root-owned directories (0700). The sudoers fragment is validated first. Only fixed catalogue installation/report/job reads are granted; arbitrary packages, package-manager options and internal worker commands are rejected. Setup installs no apps and starts no services. It is separate from firewall helper setup and remains unexecuted here. Refresh Applications after setup; a web restart is not needed for helper discovery. Rerun the installer after backend changes so the privileged copy matches the app.

Native transaction commands use existing OS repositories:

| Manager | Commands for a selected mapped package |
| --- | --- |
| apt | `apt-get update`, then `apt-get -y --no-remove install -- <package>` |
| dnf / dnf5 | `dnf -y install -- <package>` (dnf5 executable when dnf alias absent) |
| yum | `yum -y install -- <package>` |
| pacman | `pacman -S --needed --noconfirm -- <package>` |

Commands above describe implemented behavior; do not run placeholders literally. Dependencies and distribution package scripts are part of installation, including possible SSH/Samba service startup. No explicit service enable/start, share configuration or firewall rule changes are performed by DriftOS. Debian uses a noninteractive frontend and avoids automatic dependency-service restarts through needrestart's list mode. Package-manager defaults still apply. Pacman uses existing sync metadata: no `-Sy` partial refresh or automatic full-system upgrade is performed. If metadata/mirrors are stale, complete normal host maintenance separately and retry explicitly.

Read-only setup check:

```bash
sudo -n -- /usr/local/libexec/driftos-apps report
```

Expected envelope: `status: 200` with catalogue/OS information and recent jobs. Live privileged installs, service-start behavior and host package recovery have not been validated. Debian/Fedora/enterprise adapters are not tested on real hosts.

To revoke new operations, an administrator can remove `/etc/sudoers.d/driftos-apps` and `/usr/local/libexec/driftos-apps` after active transactions finish. This does not uninstall packages, stop services or delete private job records. Back up the helper, grant and job history before removal/upgrade when recovery is needed. Removing the helper while a detached worker runs does not cancel that worker. Do not grant blanket sudo access to apt/dnf/yum/pacman or writable project Python.

## File explorer configuration

Files needs no elevated helper. Run DriftOS as the same non-root user that signs in; Files rejects root, mismatched account UID and real/effective UID mismatches. Linux permissions/ACLs and filesystem read-only status continue to apply. The default root `/` permits browsing the account-readable host filesystem and starts in its home directory. Set a narrower root when desired; symlink navigation is deliberately disabled.

| Variable | Default | Behavior |
| --- | --- | --- |
| `DRIFTOS_FILES_ROOT` | `/` | Existing root folder for all explorer API paths; custom-root `/` means that configured folder |
| `DRIFTOS_UPLOAD_MAX_MB` | `1024` | Integer MiB per file, 1–16384; invalid values prevent startup |

Example startup configuration, using an existing directory the process account can access:

```bash
cd /home/dean/Projects/DriftOS
DRIFTOS_FILES_ROOT='/home/dean' DRIFTOS_UPLOAD_MAX_MB=1024 .venv/bin/python app.py
```

Restart is required after changing these variables. Under a custom root, Home falls back to the root if the account's home is outside it. Uploaded files are owned by the process account with mode 0600; new folders request mode 0750 subject to umask/default ACLs. No automatic executable bit or ownership change is applied.

For remote deployment, keep the existing HTTPS/authentication configuration. Proxy body-size limits must admit the configured raw file size, request buffering/temp storage must be sized appropriately, and proxy/server timeouts must allow intended upload durations. No proxy or multi-gigabyte transfer was validated here. Two simultaneous incoming uploads use request threads; retain capacity for ordinary HTTP/WebSocket traffic. No resumable upload protocol is provided.

## Container runtime prerequisites

The Containers page needs Docker or Podman CLI installed on the host and an accessible local runtime for the same non-root account that runs DriftOS. There are no new Python/JavaScript dependencies, environment settings, privileged helpers or sudoers rules. Restart the existing DriftOS process after deploying the source changes, then sign in again if its generated session key changed.

Docker prefers the account's rootless socket when present and otherwise uses the system socket; arbitrary Docker contexts/remote hosts are not supported. Podman operates locally as the service account and therefore does not show another account's or root's containers. Verify runtime access under that actual service identity, for example `docker --host unix:///var/run/docker.sock version` (substitute the rootless socket if applicable) or `podman --remote=false version`. The app reports permission failures without modifying permissions.

Granting Docker daemon access can grant extensive host privileges. Choose the host's intended rootless/system runtime policy before provisioning account access; do not run DriftOS as root or make a socket world-writable. Permission/group changes may require restarting the service's login context. No access grants were performed during implementation. Host check on 17 October 2026 found Docker installed but access denied and Podman absent; working host integration remains pending runtime provisioning.

## Share administration setup

From `/home/dean/Projects/DriftOS`, review and run this one-time administrator installer for the account running DriftOS (replace the argument if different):

```bash
sudo ./deploy/install-shares-helper.sh dean
```

This installs `/usr/local/libexec/driftos-shares` and `/etc/sudoers.d/driftos-shares`, creates root-owned configuration/state/storage directories and empty managed configuration files when missing, and grants exactly `report`, `share`, `user` and `start` broker commands. It does not install server packages, modify existing `smb.conf` or `/etc/exports`, open ports, start/enable services or create any share account. It rejects unsafe existing destination ownership/modes/symlinks. Rerun after updating broker source to deploy the reviewed helper version. Keep DriftOS running as its configured non-root Linux account.

Install the native Samba and/or NFS server packages using the OS package manager. Samba tools required: `testparm`, `smbpasswd`, `pdbedit`; account/group commands: `useradd`, `groupadd`, `gpasswd`, `nologin`; NFS requires `exportfs`. A supported systemd server unit must be installed. Samba is in the App library; the library does not yet include an NFS server entry. No installed package versions were available to verify on this host. Use the target OS's native package/service instructions.

Back up `/etc/samba/smb.conf` before changing it. On an existing standalone Samba installation, append this at the **end** of the configuration, with a fresh global section so the include is not scoped to the last external share:

```ini
[global]
    include = /etc/samba/driftos-shares.conf
```

Ensure the effective server role is `standalone server` and passdb backend is exactly `tdbsam` or `smbpasswd`. SMB password administration refuses Unix password synchronization; its effective `unix password sync` must be `no`. For a clean standalone configuration, the following is an illustrative minimal starting point, to review against local policy before deployment (do not replace an existing configuration wholesale):

```ini
[global]
    workgroup = WORKGROUP
    server role = standalone server
    security = user
    passdb backend = tdbsam
    unix password sync = no
    map to guest = Never
    include = /etc/samba/driftos-shares.conf
```

Validate with `testparm -s`. The helper creates no main Samba configuration. NFS uses `/etc/exports.d/driftos.exports`, loaded by the native server/exportfs; preserve `/etc/exports` and other `.exports` files. Services are not automatically started when saving shares. Use the page's confirmed Start control only after reviewing all native definitions; it may publish existing external shares too. Boot enablement, firewall rules, network binding, SMB signing/encryption, NFS version selection, Kerberos and TLS are native administrator configuration outside this page. Use HTTPS for DriftOS over a network because share-password forms carry credentials; NFS IP allowlisting is not password authentication or transport encryption. Keep shares on the intended trusted network and provision firewall access separately.

First-use order: install server tools → install helper → configure/validate SMB include if applicable → refresh Shares → create an SMB share user → add share → start the relevant server if inactive → test a client connection. On 18 October 2026 only the application/fixtures were verified; this host lacked the required servers/helper, and these installation commands were not executed. If the helper must be removed, remove its sudoers grant first; removing source files alone does not revoke an installed helper. Keep share definitions, native accounts and data until an administrator has reviewed their retention.

## Automated GitHub/systemd installation

The Bash installer is `deploy/install.sh`. It expects a server booted with systemd, an existing non-root Linux account with an executable interactive shell and valid PAM password, public GitHub/Python/native-repository network access, and curl/Bash/sudo for the bootstrap command. It supports Debian/Ubuntu through apt and Fedora/RHEL-compatible families through dnf/dnf5/yum. Other OS families must use the manual procedure. Python 3.10+ is required; an older server Python is rejected after prerequisite provisioning. No host install has been executed here.

The source repository is [deanralph/DriftOS](https://github.com/deanralph/DriftOS). Replace `dean` below with the existing server account. `ref=main` tracks the current branch; using a reviewed full commit SHA pins both bootstrap and application code. The command downloads successfully to a temporary file before executing it; it does not execute a partially downloaded pipe.

```bash
( set -e; repo="deanralph/DriftOS"; ref="main"; installer=$(mktemp); trap 'rm -f "$installer"' EXIT; curl -fsS --proto '=https' --connect-timeout 15 --max-time 60 "https://raw.githubusercontent.com/$repo/$ref/deploy/install.sh" -o "$installer"; sudo bash "$installer" --repo "$repo" --ref "$ref" --user dean --helpers all --sharing both --yes )
```

That example explicitly opts into all three administrative helpers plus SMB/NFS packages. `--sharing smb`/`both` also configures the managed Samba include and effective `unix password sync = no`; this changes password-synchronization policy for the native server, after backing up its main configuration. Existing Samba must be standalone with a supported local backend. Package scripts can start native services. Review the intended repository and flags before running with sudo. No private-repository token flow is provided.

To preview locally, without root, downloading source or changing the server:

```bash
bash deploy/install.sh --repo OWNER/REPO --user dean --helpers all --sharing both --plan
bash deploy/install.sh --user dean --print-unit
```

| Option | Behavior |
| --- | --- |
| `--repo OWNER/REPO` | Required public repository; no arbitrary URL/token input |
| `--ref REF` | Branch/tag/full commit; default `main`; refs resolved before source download |
| `--user USER` | Existing account, default sudo caller; root/no-login/missing accounts rejected |
| `--helpers none` | Default; skip helper installs without revoking existing grants |
| `--helpers firewall,apps,shares` / `all` | Explicit narrow privileged helper setup/update |
| `--sharing smb`, `nfs`, `both` or `smb,nfs` | Optional native packages; implies shares helper; SMB include/local-password policy configured |
| `--yes` | Accept the printed plan without terminal confirmation |
| `--plan` | Print selected actions only, with no network/root requirement |
| `--print-unit` | Print systemd configuration only |

The installer creates root-owned `/opt/driftos` source, its account-owned `.venv`, root-only `/etc/driftos/driftos.env`, `/etc/systemd/system/driftos.service`, and `/opt/driftos/INSTALLATION` recording repository/ref/resolved commit. New signing keys are generated directly into mode-0600 configuration, never printed. Existing private configuration is preserved after validating the account and key; it is not shell-executed. Existing user-owned application roots, unsafe administrative paths, conflicting listeners (when DriftOS is not already active) and systemd drop-ins require manual review/migration before installation. Keep free disk space for a new download/virtualenv plus a complete backup of the former application.

After successful install, run this **on your computer**, replacing SERVER_IP and account:

```bash
ssh -N -L 18090:127.0.0.1:8090 dean@SERVER_IP
```

Open `http://127.0.0.1:18090`, sign in with the server account's Linux password, and verify Overview, Files and Terminal. No port 8090 firewall exposure is required. The installer does not create an account or set its password. A working HTTP health response does not prove PAM login. Native package prerequisites can also be provisioned separately when constrained by local repository policy.

Operate the service with:

```bash
sudo systemctl status driftos --no-pager
sudo journalctl -u driftos -f
sudo systemctl restart driftos
sudo systemctl stop driftos
sudo systemctl disable --now driftos
```

Rerun the installer with the desired reviewed ref and the same selected user/helper flags to update. It rebuilds the virtualenv and restarts the service, ending current logins/shells. Existing signing key and settings persist; unchanged/skipped helper flags leave installed privileged copies untouched. Update all previously installed helpers when deploying corresponding backend changes. Public downloads and package availability are required again on upgrades. The installer retains complete application/unit/environment backups under a private `/var/backups/driftos/install-*` directory, with no automatic pruning.

For direct HTTPS access, configure the reverse proxy separately using this page's terminal/upload requirements, then edit the private environment with `sudoedit /etc/driftos/driftos.env`: set `DRIFTOS_HTTPS=1` and `DRIFTOS_ORIGIN` to the exact HTTPS origin, and restart. Existing HTTPS settings are preserved by installer updates. Docker/Podman runtime installation/socket policy, firewall rules and native sharing boot enablement remain separate. No live target-server installation, authentication, network/TLS or sharing-client acceptance has been verified here.

### Minimal-server administrative directories

The installer creates missing standard administrative directories such as `/var/backups` only after validating that their parent is root-owned, a real directory and not group/world-writable. Existing directories are checked without changing ownership or mode. Existing symlinks (including dangling links), non-root ownership and writable administrative directories remain errors. This fixes the initial installer’s incorrect rejection of minimal server images where `/var/backups` does not exist. Rerun the current GitHub installer command to obtain the fix; do not broadly chmod/chown `/var` or bypass path validation.

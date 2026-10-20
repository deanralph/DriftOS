# Architecture & tools

Browser → Flask/Jinja application → psutil and Linux PAM. HTML renders on the server, vanilla JavaScript fetches `/api/stats`, and native progress elements display usage. No CDN, frontend build system or database is required. `python-pam` authenticates and checks account status against the configured PAM service. Passwords are handled transiently and never intentionally logged or persisted.

| Path | Purpose |
| --- | --- |
| `app.py` | Routes, PAM, sessions, CSRF, throttling, metric collection |
| `templates/` | Login and dashboard Jinja templates |
| `static/driftstream.css` | Unmodified shared DriftStream UI v0.2.0 |
| `static/app.css`, `static/app.js` | Responsive layout and live dashboard |
| `tests/test_app.py` | Authentication boundary and real metric tests |
| `docs/wiki/` | Canonical local documentation |
| `requirements.txt` | Exact installed dependency versions |

Verified environment: Python 3.14, Flask 3.1.3, psutil 7.2.2, python-pam 2.1.0, Gunicorn 26.2.0 and Node 26.8.2 (syntax verification only). Local development binds TCP 127.0.0.1:8090, HTTP. No external runtime APIs. WikiStream is documentation infrastructure only, configured in `wikistream.json`.

## Terminal integration (v0.2)

Browser xterm.js → same-origin WebSocket `/ws/terminal` → Flask-Sock/simple-websocket → PTY master → isolated-session helper → account's interactive shell. `terminal_service.py` owns bounded connections, incremental UTF-8 decoding, resize/input validation and process cleanup. `terminal_worker.py` attaches the controlling terminal before exec; the threaded web server does not use `preexec_fn` or a Python fork callback. The shell starts in the account's home with its configured shell and a small allowlisted environment; DriftOS/WikiStream environment secrets are not inherited. User shell startup files still run and may load user-specific environment or credentials.

New paths: `templates/workspace.html` shared navigation; `templates/terminal.html`; `static/terminal.js`; `static/vendor/` self-hosted xterm assets and MIT license notices; `tests/test_terminal.py`; `package.json`/`package-lock.json` plus `scripts/vendor-terminal.mjs` for optional asset regeneration. Runtime does not need Node/npm.

Verified additions: Flask-Sock 0.7.0, simple-websocket 1.1.0, wsproto 1.3.2, h11 0.16.0, xterm.js 6.0.0 and addon-fit 0.11.0. Test-only websocket-client 1.9.2 is pinned in `requirements-dev.txt`.

Login leases and revocation events now live in process memory. Cookies contain a random login ID; all protected routes require its live lease. Restart revokes logins even with a stable signing key. WebSockets check both exact Origin and a CSRF token sent in the opening message. Only the terminal page permits generated inline styles for xterm; script loading stays self-only. No CDN or transcript logging is used.

## Firewall integration

Browser `static/firewall.js` → authenticated GET/POST `/api/firewall` → `firewall_service.py` → noninteractive `sudo` → `/usr/local/libexec/driftos-firewall`. The installed helper is a standalone copy of `firewall_backend.py`, invoked using isolated system Python (`/usr/bin/python3 -I`) and importing no writable project modules. It accepts only `report` or fixed UFW/firewalld on/off operations with a validated report hash. Privileged executable discovery uses only system directories and subprocesses use argv lists, never a command shell. The app verifies root ownership and absence of group/world write permission or symlinks on the helper and its parent directories.

`deploy/install-firewall-helper.sh` stages a root-owned executable and user-specific sudoers entry. It does not enable/disable any firewall or add rules. The web application remains the configured non-root user; write routes also require that same process UID. No new Python/npm runtime dependency was introduced for firewall management.

A root-owned `/run/driftos-firewall.lock` serializes helper operations. Each write re-reads the report and checks its SHA-256 revision before selecting a fixed command, then reads back the result. Host administrators can still change firewall state outside the helper; there is no global transaction across external tools. Commands have timeouts and changes are never automatically retried.

UFW uses `status verbose`, plus saved `show added` commands while inactive. firewalld uses state, active zones/list-all and active policy information; start/stop occurs through its systemd service and is refused when cleanup-on-exit is disabled/unreadable. nftables JSON and both IPv4/IPv6 iptables filter rules are read-only. Summaries do not model packet traversal, rule precedence, named-service expansion, Docker/cloud firewalls or reachability.

## Curated package installation

`templates/apps.html` and `static/apps.js` provide six catalogue cards, filtering and polled job progress. `apps_backend.py` contains the fixed catalogue, per-manager package mapping, package-database queries and a standalone root broker. `apps_service.py` calls the installed broker through fixed noninteractive sudo argv; unconfigured access still permits unprivileged installed-state discovery. `deploy/install-apps-helper.sh` stages the separate privilege grant. No new Python or npm dependency was introduced.

Package mappings: btop/htop/tmux/rsync/samba have matching package names across supported managers. The OpenSSH server maps to `openssh-server` for apt/dnf/yum and `openssh` for pacman. Installed status comes from dpkg-query, rpm or pacman, rather than command presence. Failed/unrecognized database queries produce Unknown instead of falsely reporting absence. Query timeouts are two seconds per package.

The root-owned `/usr/local/libexec/driftos-apps` is an isolated-system-Python copy of the standalone backend; it imports no writable project modules. Root entry points are `report`, `install <catalogue-id> <manager>` and `job <32-hex-id>`. The internal worker is not granted in sudoers. Helper/parent paths and state-directory ownership/permissions are checked. Operations use fixed argv, never shell command interpolation or arbitrary package names.

Submission re-detects the OS installer, rejects unknown/already-installed state, acquires `/run/driftos-apps.lock`, writes an atomic private job record and launches a detached root worker with an inherited lock FD. The worker retains the lock across all native commands and verifies package state afterward. Job records under `/var/lib/driftos/app-jobs/` retain queued/running/succeeded/failed/unknown state and at most 65,536 characters of output tail. Report includes up to ten recent jobs. Worker PID/start-time identity distinguishes abandoned operations from a reused PID. No background package transaction is killed merely because a browser request times out or the user signs out.

Verified additional host tools: pacman 7.1.0 / libalpm 16.0.1 on Omarchy 4.0.4. Other distro adapters were fixture-tested only.

## File explorer and streamed uploads

`templates/files.html` and `static/files.js` provide folder navigation, a native new-folder dialog, desktop file drop handling, the file picker and an XMLHttpRequest progress queue. `files_service.py` performs directory-fd-based listing, mkdir, regular-file download and atomic upload publication. No dependency was added; Linux/Python filesystem APIs and libc's `renameat2` are used.

The filesystem root is canonicalized from trusted startup configuration. API paths are virtual paths under it: absolute/relative slash separators are supported, but `.`/`..`, invalid names, control characters and the reserved partial-upload prefix are rejected. Every navigated directory component is opened with `O_DIRECTORY|O_NOFOLLOW`; downloads open the final component with `O_NOFOLLOW|O_NONBLOCK` and verify regular-file type. Symlink/special entries may be listed but cannot be opened/downloaded. A hash of directory device/inode identifies the viewed destination and is required for writes, rejecting a path replaced since it was listed.

Uploads use an octet-stream request body and URL-encoded filename/path headers plus a CSRF header, avoiding multipart spooling and allowing 64 KiB reads directly to a private temporary file in the destination. The ordinary 8 KiB form limit remains in place; only `/api/files/upload` gets the configured upload limit. Two concurrent server upload slots are available; each browser queue sends one file at a time. Login revocation/expiry is checked during receipt and before publication.

Completed files are fsynced, atomically renamed using Linux RENAME_NOREPLACE, then the directory is fsynced. If that API is unsupported, a same-directory non-overwriting hard-link/unlink fallback is used. Filesystems supporting neither method reject uploads rather than overwrite. Exception paths remove the current partial file when cleanup can run. Temp names use `.driftos-upload-<random>.part`, are excluded from listings and cannot be addressed through Files APIs. Downloads use attachment/octet-stream with the app's existing no-store/nosniff headers.

## Container runtime adapter

`containers_service.py` invokes installed Docker/Podman CLIs with fixed argv, no shell and no sudo. `templates/containers.html` and `static/containers.js` implement the authenticated inventories and lifecycle controls using the existing DriftStream stylesheet. The sidebar version is v0.6.

Docker explicitly selects `unix:///run/user/<uid>/docker.sock` when that path exists, otherwise `unix:///var/run/docker.sock`. Podman uses `--remote=false` and this account's local storage. A minimal subprocess environment includes account HOME/USER/LOGNAME, fixed PATH, locale and `/run/user/<uid>` as XDG_RUNTIME_DIR; service secrets and remote endpoint environment variables are not inherited. Native local user configuration can still affect runtime behavior. Separate runtime version checks probe connectivity. Inventory parsing supports Docker JSON lines and Podman JSON arrays, with case-insensitive field lookup and structured Podman port mappings. Responses expose an allowlist of display fields, not environment variables or full inspect data.

Two commands can execute concurrently per worker. Reads time out after 12 seconds; lifecycle operations after 35 seconds (stop/restart request a 10-second grace period). CLI output is spooled to private temporary files; inventory reads reject output above 4 MiB, and logs read the last 200 lines with a final 64 KiB text cap. Temporary disk output can grow while a command runs; these are not streaming quotas. stdout/stderr log streams are grouped, not chronologically merged. No automatic command retries occur.

CLI format references: [Docker container ls](https://docs.docker.com/reference/cli/docker/container/ls/) and [Podman ps](https://docs.podman.io/en/latest/markdown/podman-ps.1.html).

## Share administration architecture

`templates/shares.html` and `static/shares.js` reuse DriftStream panels, buttons, inputs and square dialogs. `shares_service.py` is the non-root subprocess bridge. `shares_backend.py` is a standalone Python-standard-library broker installed as `/usr/local/libexec/driftos-shares`, with Python isolated mode and no imports from writable project code. `deploy/install-shares-helper.sh` stages the root-owned copy, managed directories and exact sudo command rules. No new Python/npm dependencies are added. Sidebar version is v0.7.

Authenticated browser → Flask same-account/CSRF check → `sudo -n -- /usr/local/libexec/driftos-shares <report|share|user|start>` → fixed native commands. Request JSON is supplied on stdin and limited to 8192 bytes. Passwords only pass to `smbpasswd -s -a` through stdin; they never appear in argv, broker output, persistent state or job logs. Password input is cleared in the browser on submission/close. The bridge uses a minimal environment and a 90-second timeout; native commands default to 15 seconds, service start to 30. Operations are synchronous and never automatically retried.

A root-only file lock serializes reporting and mutation. Mutations require a SHA-256 revision of state plus managed SMB/NFS configuration and the main Samba configuration. Stale requests return 409. Managed writes use private same-directory temporary files, fsync and atomic rename; `state.previous.json` keeps the previous metadata revision. This is not a multi-file transaction or a complete system backup. Failed configuration application restores the former managed file and group membership, then attempts a reload of the former configuration. A failed rollback reload is explicitly reported as unconfirmed.

SMB requires standalone Samba and a local `tdbsam`/`smbpasswd` backend; password administration additionally requires `unix password sync = no`. Generated sections use `valid users`, no guest access, forced dedicated groups, restricted create/directory masks and no symlink following. Each share gets `ds_s_<name>` and a root-owned setgid folder mode 2770. NFS definitions use `sync,subtree_check,all_squash,anonuid=65534,anongid=<share-gid>` and explicit `ro`/`rw`. No arbitrary path, options, command, username or service unit can be supplied through the API. Managed names are 1–20 lowercase letters/digits/underscores/hyphens starting with a letter. Limits: 64 shares, 64 share users, 32 selected users per SMB share and 16 clients per NFS share.

Detection supports `smb.service`/`smbd.service` and `nfs-server.service`/`nfs-kernel-server.service`. SMB configuration is validated using `testparm -s`, including checking effective presence of an enabled managed section. Active SMB uses `systemctl reload`; active NFS uses `exportfs -ra`, which reconciles the host's full configured export table, including external definitions. Saving to an inactive service does not start it. Confirmed Start may activate external shares too; no service is enabled at boot by DriftOS.

Native references: [Samba configuration](https://www.samba.org/samba/docs/current/man-html/smb.conf.5.html), [smbpasswd](https://www.samba.org/samba/docs/current/man-html/smbpasswd.8.html), [testparm](https://www.samba.org/samba/docs/current/man-html/testparm.1.html), [exports](https://man7.org/linux/man-pages/man5/exports.5.html), [exportfs](https://man7.org/linux/man-pages/man8/exportfs.8.html).

## Server installer flow

`deploy/install.sh` is a standalone Bash entry point with embedded standard-library Python. After argument/OS/user/systemd validation and confirmation (or `--yes`), it installs prerequisites via apt-get or dnf/dnf5/yum. An exclusive lock under `/run/driftos-installer/lock` prevents concurrent installs. Full 40-hex refs skip GitHub API resolution; other refs use the public commit endpoint. Codeload downloads are HTTPS-only, have connect/transfer timeouts and a 50 MiB compressed-size limit. Extraction rejects traversal/absolute paths, multiple roots, duplicate paths, links/special files, more than 20,000 members and over 256 MiB declared expansion. It skips `.git`, `.venv`, `node_modules`, `__pycache__`, `.env` and `api.json`; repository ownership/setuid bits are not restored. Commit pinning identifies content but is not signature verification or an independent trust decision.

Application source is root-owned under `/opt/driftos`; only `.venv` is owned by the selected service user. The virtualenv is rebuilt at its final path because executable shebangs are absolute. Pip and venv creation run with that account's HOME and a minimal environment. The root-only environment is parsed as data, never sourced as shell. Existing service-user/signing-key configuration is preserved and must match the selected account; new configuration uses a random signing key, loopback HTTP, existing PAM login policy and existing file-explorer defaults.

The generated `driftos.service` uses Type=exec, User=<account>, `/etc/driftos/driftos.env`, fixed `/opt/driftos` working directory, gthread/one worker/twelve threads, 120-second Gunicorn timeout, `127.0.0.1:8090`, journald stdout/stderr, restart-on-failure and a 45-second systemd stop timeout. Host PAM/sudo/PTY capabilities are retained; no root web process, NoNewPrivileges, filesystem sandbox or public listener is configured. Existing systemd drop-ins are rejected because they could override those settings. Existing user-owned/symlink/group/world-writable administrative destinations are rejected; this is not an automatic migration of earlier manual deployments.

Core deployment backs up prior app/unit/private environment, stops/replaces the app, builds dependencies, writes the unit, enables/starts and polls native active state plus JSON HTTP health. Failure before the health checkpoint attempts restoration of app/unit/env and prior active/boot-enabled state; restoration errors are reported for manual recovery. Native packages are retained. Optional helper/package/Samba setup runs after this checkpoint and is not included in core rollback. The app can therefore remain installed while optional setup returns a failure. Skipped helper flags do not revoke or update existing helper copies. No native sharing service is explicitly started/reloaded/boot-enabled, but package scripts may start services.

## LAN listener and installer firewall integration

`--lan` selects `0.0.0.0:8090` in the generated Gunicorn unit and port-conflict probe. Runtime health remains checked through loopback. The existing private environment is backed up before LAN migration; `DRIFTOS_HTTPS` is set to `0` and `DRIFTOS_ORIGIN` removed so requests and terminal WebSockets derive their exact origin from the browser's host. Signing key/account and unrelated settings persist. Default/`--localhost` keeps the loopback listener and existing HTTPS/origin values.

After core health success, LAN firewall configuration detects active UFW and firewalld. Two active managers cause a failure without rule writes. UFW uses persistent `allow from <CIDR> to any port 8090 proto tcp` rules with a DriftOS comment. Firewalld adds IPv4 source-scoped rich rules to runtime and permanent configurations for each active zone (default zone if none); it does not reload or copy runtime configuration wholesale. No active supported manager means no firewall changes, with an explicit manual-policy notice. Existing nftables/iptables/cloud/router policies and broad allows/denies remain unchanged.

Client defaults: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`. Repeat `--lan-cidr` to replace these with up to 16 explicit IPv4 CIDRs; canonical addresses/prefixes are checked and /0 is rejected. `--no-firewall` skips additions. This does not provide IPv6 listening/rules or a new API. Native firewall commands are only tested with fixtures, not on the implementation host.

## Standalone uninstaller

`deploy/uninstall.sh` is standalone Bash with embedded standard-library Python; it works from a downloaded temporary file without importing the project being removed. `--plan` and `--help` require no root/network and perform no writes. Actual removal requires root, a booted systemd host, Python 3 and flock. It validates fixed administrative paths/ownership, rejects unsafe parent directories, validates the root-owned installation marker and refuses application symlinks or mounted filesystems inside the application tree. Named helper/config symlinks are backed up and unlinked as links without following their targets; service symlinks other than a `/dev/null` mask require manual review. Linux fd-safe `shutil.rmtree` is required for application removal.

The uninstaller holds `/run/driftos-installer/lock` plus app/firewall/share broker locks before service teardown. A tracked package/helper job in progress causes refusal; it does not kill a package transaction. These coordination files are retained to avoid unlinking a live lock and allowing a second process to lock a replacement inode. It stops/disables the unit, backs up existing unit/env/helpers/sudo grants under `/var/backups/driftos/uninstall-*`, revokes the grants, removes marked source/venv and named files, reloads systemd and clears failed state. Service stop/disable errors prevent file removal. Missing/already-removed files are tolerated. A private `REMOVED.json` records targeted paths and retention, without credential contents.

No package manager, firewall mutation, user/group removal, share unexport or native sharing-daemon stop is invoked. Existing active services/shares and user data remain operational under their native configurations. This is targeted app cleanup, not a transaction over hosted workloads. Live systemd/root removal is unverified; filesystem and shell command behavior is covered by isolated fixtures.

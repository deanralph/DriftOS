# Tests & verification

## Repeatable procedures

From `/home/dean/Projects/DriftOS`, after installing requirements:

```bash
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
.venv/bin/python -m py_compile app.py tests/test_app.py
```

Expected for the current version: 136 unittest cases pass, syntax checks exit zero. Terminal tests additionally require `requirements-dev.txt`, loopback socket access and host PTY support. Tests use Flask's in-process test client. PAM success/failure is mocked, but metrics are collected from the actual environment and terminal tests execute real local shells. Tests cover anonymous access rejection, CSRF rejection, failed login and throttling, session/login/logout lifecycle, real metric shape/root mount, configured account restrictions, headers/static assets, and 503 metric failure handling. No production credentials are required.

Manual target-host acceptance: sign in with the configured Linux account; verify wrong password fails; verify locked/expired accounts fail according to PAM policy; compare metrics with host tools; refresh; disconnect service and check stale warning; logout and confirm `/api/stats` returns 401. Test desktop/mobile layouts and HTTPS Secure-cookie behavior on deployment.

## Execution record — 17 October 2026

Source revision unavailable: workspace is not an initialized Git repository. Environment: local Linux, Python 3.14, Flask 3.1.3, psutil 7.2.2, python-pam 2.1.0, Node 26.8.2. The three commands above ran successfully: seven tests passed, JavaScript and Python syntax checks passed. The login screen was opened and visually inspected in the Codex browser at localhost:8090. No actual Linux password login was attempted. Target PAM success, remote/TLS deployment, browser dashboard interactions, backup restore and mobile visual inspection remain unverified.

## Execution record — 17 October 2026, terminal integration

Source revision remains unavailable (no initialized Git repository). Installed/runtime environment as above plus Flask-Sock 0.7.0, simple-websocket 1.1.0, wsproto 1.3.2, h11 0.16.0; test-only websocket-client 1.9.2; browser xterm.js 6.0.0 and addon-fit 0.11.0.

```bash
cd /home/dean/Projects/DriftOS
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
node --check static/terminal.js
.venv/bin/python -m py_compile app.py terminal_service.py terminal_worker.py tests/test_app.py tests/test_terminal.py scripts/publish_docs.py
```

Executed result: 20 tests passed. The terminal tests bind a disposable loopback HTTP/WebSocket server, mock PAM only for fixture logins, and launch real account PTY shells. Positive cases exercised harmless `printf`, `stty size`, `sleep`, Ctrl+C and `exit`. Verified terminal resizing, normal exit, disconnect child-job cleanup, logout revocation including copied cookies, absolute login expiry, idle timeout and service environment secret exclusion. Negative cases covered anonymous/unsigned cookies, bad Origin, invalid CSRF/dimensions, oversized input, duplicate terminals, global capacity and root/UID mismatch. Existing dashboard/auth/metrics cases still pass. Python/JavaScript syntax checks passed.

Browser verification used a separate disposable UI fixture with simulated output and no command execution. Verified connect, xterm rendering, focus, disconnect/new-terminal controls, retained output and no horizontal overflow at the browser's default desktop size; fixed a grid overflow discovered during inspection. Final frontend loaded without JavaScript/CSP errors. This browser fixture does not establish actual PAM authentication; real PTY execution is verified separately by the integration suite. No production password was entered. Real-password PAM, mobile visual acceptance, TLS/reverse-proxy WebSockets and crash/recovery behavior remain unverified.

## Execution record — 17 October 2026, terminal layout correction

Source revision unavailable (no Git repository); same local Linux/Python/browser environment as the terminal integration record. Browser check used a simulated-output fixture, without executing shell commands. Before correction, the rendered terminal bottom was 828.375 px while the stage/status boundary was 818.375 px (10 px overlap). After moving padding onto the stage, the rendered terminal ended at 806.375 px, 12 px above that boundary. Confirmed no horizontal document overflow and removal of the sidebar promotional text. Re-ran `.venv/bin/python -m unittest discover -s tests -v`: 20 tests passed. Mobile-specific visual verification remains pending.

## Execution record — 17 October 2026, firewall manager

Source revision unavailable (workspace not initialized as Git). Same Linux/Python/browser environment as prior records. UFW 0.36.2 is installed on the development host alongside nftables/iptables tools. A read-only `systemctl is-active ufw` returned active, but that service result is not used as proof of live rules. `sudo -n /usr/bin/ufw status verbose` returned “a password is required”; live UFW rules/state remain unverified. No host firewall settings were changed and the privileged helper/authorization were not installed.

Executed commands, from `/home/dean/Projects/DriftOS`:

```bash
.venv/bin/python -m unittest discover -s tests -v
node --check static/firewall.js
.venv/bin/python -m py_compile app.py firewall_backend.py firewall_service.py tests/test_firewall.py
sh -n deploy/install-firewall-helper.sh
```

Result: 41 tests passed; syntax checks passed. Firewall tests use fixtures/mocks for all command executions and changes. They cover UFW status/defaults/IPv4/IPv6/rule parsing and saved inactive rules; firewalld active zones/policies and cleanup-on-exit restriction; raw nftables and both iptables address families; no manager/permission failures; active-manager conflicts and unknown peers; stale hash rejection; fixed noninteractive helper argv; extra/injected argument rejection; timeout without retry; API login/CSRF and invalid parameters; unconfigured helper refusal. Previous real PTY/WebSocket regression tests still pass. No firewall enable/disable test was performed on the host.

Browser acceptance used a disposable simulated-report server with no access to firewall execution. Verified reports, on/off switch state, saved-versus-live labels, the Unknown/disabled state before admin setup, and failed-change rollback of the displayed switch plus disabled controls until Refresh. That simulated test does not establish privileged firewall integration. Installer execution, sudoers authorization, actual on/off behavior and network access/recovery remain pending administrator setup and controlled host acceptance.

After adding the visible administrator setup command, re-ran the firewall-only suite (`.venv/bin/python -m unittest discover -s tests -p 'test_firewall.py' -v`): all 21 firewall tests passed; `node --check static/firewall.js` also passed.

## Execution record — 17 October 2026, app library

Source revision unavailable (not a Git repository). Same local Linux/Python/browser stack; read-only host inspection identified Omarchy 4.0.4, pacman 7.1.0 / libalpm 16.0.1. `apps_backend.report()` actually selected pacman and reported btop 1.4.7-1, tmux 3.7_c-1, rsync 3.5.0-1 and OpenSSH 10.5p1-1 installed; htop/Samba missing. This proves local package-database discovery, not repository availability or service activity.

Executed from `/home/dean/Projects/DriftOS`:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s tests -p 'test_apps.py' -v
node --check static/apps.js
.venv/bin/python -m py_compile apps_backend.py apps_service.py app.py
sh -n deploy/install-apps-helper.sh
```

Full suite: 60 tests passed. After adding dnf5 executable fallback, all 19 app tests passed again. Python/JS/shell syntax checks passed. Tests cover native OS/ID_LIKE selection and dnf→yum/dnf5 fallback, foreign-manager refusal, package-name/argv mapping, installed/missing/unknown DB states, queued persistent job records and inherited locking, busy/duplicate submissions, worker success verification/output, failed native commands without retry, lost worker identity, job-ID traversal/injected input rejection, credential-like log redaction, API auth/CSRF, and missing setup. Native installer subprocesses are mocked; worker records use temporary fixtures. Existing real PTY/WebSocket tests still pass. No actual host packages or services were changed.

Browser acceptance uses an isolated simulated app server which cannot invoke installation commands. Verified catalogue layout, filtering, queued/completed job progress and installed-card refresh; simulated setup/error states were also checked. No root helper installation, real apt/dnf/yum transaction, live pacman installation, actual service startup, machine-reboot recovery or package rollback was performed. These remain pending controlled administrator acceptance.

## Execution record — 17 October 2026, Files and menu cleanup

Source revision unavailable (not a Git repository); same local Linux/Python/Flask environment as prior records. Executed from `/home/dean/Projects/DriftOS`:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_files.py' -v
.venv/bin/python -m unittest discover -s tests -v
node --check static/files.js
.venv/bin/python -m py_compile files_service.py app.py tests/test_files.py
```

Results: all 19 file-specific tests passed, then the full suite passed all 79 tests. JS/Python syntax checks passed. File tests perform real I/O only in disposable temporary roots: exact bytes, empty/Unicode files, modes, >8 KiB upload success, upload cap, incomplete/failed streams and late auth revocation cleanup, non-overwrite of regular/symlink destinations, path traversal and symlink-folder rejection, folder identity mismatch, mkdir, regular-only attachment download (including HTML), FIFO refusal, hidden files/pagination/cap, fallback atomic hard links, request authentication/CSRF, root refusal, busy slots, error mappings and unnumbered navigation. No normal host files were modified by these tests.

Browser verification used a separate explorer restricted to `/tmp/driftos-files-ui-7wwo41h_` with harmless fixture files. Opened Documents, selected `/tmp/driftos-desktop-upload.txt` using the browser file chooser, and verified automatic HTTP upload/100% progress. Disk comparison confirmed the exact 37 bytes in Documents and absence of that file in the parent; the same browser session successfully created an Upload archive subfolder. Duplicate/non-overwrite handling was verified by automated tests. Folder navigation and number-free menu rendering were visually checked. The browser test did not exercise a physical desktop drag gesture; that handler uses the same enqueue/upload path as the verified picker. Native drag/drop across desktop/browser combinations, multi-gigabyte/proxy transfers, full-disk/crash recovery and network-filesystem publication remain manual acceptance items.

A follow-up late directory-fsync failure test verifies that an already published file is retained and the API reports uncertainty without retrying. Re-ran the full suite after that change: all 80 tests passed (20 file tests plus the existing 60); Python/JavaScript syntax checks passed again.

## Container management execution record — 17 October 2026

Source revision unavailable (workspace is not an initialized Git repository). Environment: existing local Linux/Python 3.14/Flask 3.1.3/Node 26.8.2. From `/home/dean/Projects/DriftOS`:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_containers -v
.venv/bin/python -m py_compile containers_service.py app.py
node --check static/containers.js
```

The full suite passed 93 cases. After refining permission error reporting, the 13 container cases were rerun successfully; Python and JavaScript syntax checks passed. The new tests cover Docker JSON lines, Podman arrays/ports/case handling, allowlisted inventory fields, missing/unreachable runtimes, fixed lifecycle argv, invalid IDs/actions, command failure/timeout, minimal environment and local endpoint selection, bounded logs, login/session and CSRF boundaries. Native container mutations are mocked.

A separate localhost:8091 Flask UI fixture with simulated Docker/Podman data verified runtime switching, all four inventory tabs, search/no-match behavior, start/stop confirmation and state refresh, and log display. A desktop screenshot was reviewed; table minimum widths were increased to avoid names breaking across characters. Successful real runtime operations and mobile visual behavior remain unverified. The fixture has no host container operations and is stopped after testing.

Read-only native detection outside the sandbox confirmed Docker installed but local access denied and Podman absent. No actual container lifecycle action, permission grant, package installation or remote runtime access was performed. Expected target acceptance after provisioning: compare inventories with the native CLI; create a disposable workload independently, verify start/stop/restart and logs through DriftOS, then remove it through the native tool. Do not test lifecycle controls on production workloads without planning service interruption.

## Share administration execution record — 18 October 2026

Source revision unavailable: workspace is not an initialized Git repository. Environment: existing local Linux, Python 3.14, Flask 3.1.3 and Node 26.8.2. From `/home/dean/Projects/DriftOS`:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_shares -v
.venv/bin/python -m py_compile app.py shares_backend.py shares_service.py tests/test_shares.py
node --check static/shares.js
sh -n deploy/install-shares-helper.sh
```

Final full suite: 121 tests passed, including 28 share tests. Python/JavaScript/shell syntax checks passed. Tests cover strict name/boolean/password/client validation, config injection/path rejection, provisioned-user selection, no-guest SMB generation, squashed NFS generation, stale revision rejection, fixed commands, no-login account provisioning, existing account/folder rejection, pending password recovery, Unix password sync rejection, atomic metadata/previous snapshot, retained share data, reload rollback and restored group membership, missing-helper behavior, login/CSRF/process identity and form-field allowlisting. Native account/group/Samba/NFS/systemd mutations are mocked; temporary filesystem fixtures exercise metadata/config writes without host administration.

A separate localhost:8091 Flask fixture with in-memory services/shares/users verified browser SMB share creation, NFS editing/disabling with a retained definition, user enable/disable confirmation and refreshed flags, and the Add user form layout. It did not provision real accounts/passwords, execute exports or modify services. A hidden-field CSS issue discovered during form checks was fixed; SMB forms now hide NFS inputs and vice versa. Desktop screenshots were reviewed. Mobile layout, real password/client authentication, network mounts, reload behavior against installed servers, helper installation, service reboot behavior and recovery remain unverified.

Read-only inspection both inside and outside the sandbox found required Samba/NFS tools and supported service units absent and the new helper not installed. No host configuration, privileged helper, account, group, service, firewall or export was changed. Target acceptance after deliberate provisioning: test allowed/denied SMB users, user disable/reconnect, both read-only/write shares, NFS allowed/denied client networks and squash identity, inactive-service save versus explicit start, stale revision, failed reload recovery, and consistent backup/restore using disposable data first. The unit suite does not prove native interoperability or production deployment.

## Server installer execution record — 19 October 2026

Source revision unavailable: this workspace is not an initialized Git repository. Environment: existing local Linux/Python 3.14/Node 26.8.2 plus host systemd-analyze. Executed from `/home/dean/Projects/DriftOS`:

```bash
bash -n deploy/install.sh
bash deploy/install.sh --repo example/DriftOS --user dean --helpers all --sharing both --plan
.venv/bin/python -m unittest tests.test_installer -v
.venv/bin/python -m unittest discover -s tests -v
```

All passed: 12 offline installer cases and 133 cases in the full regression suite. Tests exercise argument injection rejection, no-root/no-network plan output, default opt-out and sharing/helper selection, unit generation, archive private/generated-file exclusion, traversal/absolute path/multiple-root rejection, links/devices, duplicate/missing assets, expansion limit, private environment creation, secret/config preservation and non-execution of shell-like environment values. They do not execute native package management, root filesystem installation or service changes.

The rendered systemd unit was checked with `systemd-analyze verify /tmp/driftos-installer.service` outside the sandbox; it passed after substituting `/usr/bin/true` for the unavailable target installation executable. The initial sandbox check could not use the required systemd sockets. This validates unit directives, not the target executable, actual service startup or runtime privileges. Bash syntax and offline fixtures passed; shellcheck was unavailable.

No actual GitHub repository endpoint was supplied/published or downloaded by the installer. No host installer, sudoers/helper installation, native packages, live PAM login, SMB/NFS clients, upgrade rollback or direct HTTPS deployment was executed. Target acceptance must cover a clean supported OS with a real public repo/ref, actual user/PAM login and WebSocket shell; optional helper grants; repeat installation preserving the secret; deliberately failed core health check restoring the previous service; optional-step failure retaining the core; backup recovery; and package/service behavior on each advertised distro. Do not describe these as proven by the offline suite.

## GitHub publication — 20 October 2026

After user-completed GitHub authentication, `git push -u origin main` succeeded to `https://github.com/deanralph/DriftOS.git`. `git ls-remote origin refs/heads/main` and local `git rev-parse HEAD` both returned `45efcebbf426fc97079acad7f3fa9fba522e082e`; the working tree was clean. A HTTPS download of the installer at this commit matched local `deploy/install.sh` byte-for-byte, SHA-256 `a4a847ab5d9d273ab3e336a673f4c0a2108030336d96538d063d1d4f8b5beaa4`. Credentials/`.env`, virtualenvs and Node dependencies were confirmed excluded from Git. Download verification did not execute the installer or provision a server. This record is added in a follow-up documentation commit.

## Missing administrative directory regression — 20 October 2026

On the local Linux/Python 3.14 environment, `bash -n deploy/install.sh` passed; `.venv/bin/python -m unittest tests.test_installer -q` passed 15 tests and `.venv/bin/python -m unittest discover -s tests -q` passed 136 tests. New directory fixtures mock root ownership/install operations without host changes and verify missing-directory creation, existing-mode preservation, and rejection of unsafe owners/modes, writable parents and existing/dangling symlinks. The user-reported `/var/backups` failure occurred in the previous installer’s preflight; the fix does not execute or validate a complete target-server installation. Source base: `b8c7eed`; subsequent fix commit is available in Git history.

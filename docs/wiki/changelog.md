# Documentation change log

## 17 October 2026 — Initial DriftOS implementation

Created the PAM login flow and server overview, adopting the DriftStream UI v0.2.0 shared CSS unchanged. Added protected metrics, automatic refresh, session/CSRF protection, bounded login throttling and responsive styles. App installation and terminal controls are disabled planned features.

Created overview, architecture, deployment, data-and-recovery, usage, api, verification and troubleshooting pages. Source revision unavailable (not a Git repository). Seven unit/integration cases and Python/JavaScript syntax checks passed locally; login screen visually inspected. Real-password PAM, remote/TLS deployment, backup restore and mobile/dashboard browser acceptance are unverified. See Verification for exact commands and limitations.

## 17 October 2026 — Interactive terminal (v0.2)

Added authenticated xterm.js 6.0.0 / addon-fit 0.11.0 UI and Flask-Sock WebSocket → Linux PTY integration. Added explicit connect/disconnect/new-terminal controls, keyboard interaction, resizing, clear-view and retained output. Shared DriftStream CSS remains unchanged. Applications remains planned.

Added exact-origin/CSRF checks, strict same non-root UID execution, small allowlisted child environment, bounded terminal slots/input/dimensions, 15-minute keyboard-idle cutoff and one-hour login leases. Logout revokes copied session cookies and cleans up the shell's POSIX session. Restart now revokes in-memory logins. Documented normal account permissions, shell-history persistence, detached-process and proxy limitations.

Updated all nine documentation pages, README, pinned Python runtime/test dependencies and vendored npm assets/licenses. Improved the WikiStream publisher with explicit read/reconciliation snapshots and optimistic version-checked updates. No source revision available (not a Git repository). Twenty tests passed, including real WebSocket/PTY input, resize, Ctrl+C, child cleanup and revocation; syntax checks passed. Browser controls/rendering were verified with a simulated-output fixture. Real PAM-password and remote TLS/proxy/mobile acceptance remain unverified.

## 17 October 2026 — Terminal containment and sidebar cleanup

Moved terminal spacing from xterm's measured host onto the outer stage, leaving an unpadded inner container and clipping within the stage. This prevents bottom terminal rows overlapping the card's status bar, including the mobile padding rule. Removed “Your machine. At a glance. Less digging. More doing.” from shared sidebar navigation and removed its unused text styles. Updated Usage and Verification. Browser fixture measurements confirmed containment and no horizontal overflow; the 20-test regression suite passed. Source revision unavailable (not a Git repository).

## 17 October 2026 — Firewall manager (v0.3)

Removed the terminal tagline and decorative subheading, replacing its initial prompt with connection-state wording. Added shared Firewall navigation and a functional page with manager discovery, tri-state activity, explicit rule counts/table, default policies, raw output, refresh and accessible on/off switch.

Added UFW and firewalld report/control adapters, read-only nftables and IPv4/IPv6 iptables detection, validated stale-report hashes, fixed-argument privileged helper, operation serialization, result verification and no automatic mutation retry. Staged the root-owned helper/sudoers installer; it has not been run, so live reports and switching require administrator setup. DriftOS itself remains unprivileged. No host firewall state or rules changed. Updated all nine wiki pages and README.

Forty-one tests and Python/JavaScript/shell syntax checks passed. Browser interactions used a simulated firewall fixture, including successful switches, unavailable privileges and failed-change behavior. Actual privileged firewall switching, installer authorization and lockout recovery are unverified. Source revision unavailable (not a Git repository).

## 17 October 2026 — Curated app library (v0.4)

Enabled Applications navigation and added btop, htop, tmux, rsync, OpenSSH server and Samba cards with OS/native installer selection, DB-backed installed versions, filters and progress/logs. Debian/Ubuntu uses apt-get, Fedora/RHEL selects dnf (dnf5 fallback) before yum, Arch/Omarchy uses pacman. Unknown families/missing native managers are labelled unsupported. The overview's old planned-apps panel now links to the implemented library.

Staged a separate root-owned curated-package helper and sudoers installer. Added persistent private job records, detached workers, inherited transaction lock, fixed package/command allowlists, output tail/redaction, final package verification and explicit unknown-operation recovery behavior. No full Arch upgrades, extra repositories, uninstall, share/firewall editing or explicit service starts were added. Distro package scripts may start server services. Helper setup/live installation remain unexecuted; no host packages changed.

Updated all nine wiki pages and README. Sixty regression tests passed; the 19 app tests passed again after dnf5 fallback changes. Syntax checks passed. Real read-only pacman discovery was verified; install behavior/browser jobs used mocks/simulated fixtures. Other-distro live installs, privileged setup and recovery remain unverified. Source revision unavailable (not a Git repository).

## 17 October 2026 — File explorer and number-free navigation (v0.5)

Removed all menu suffix numbers and the obsolete mobile numbered-menu selector; added Files navigation. Implemented account-level home/root browsing, breadcrumbs/Up/path entry, hidden-file visibility, page filtering/pagination, metadata, new folders and regular-file attachment downloads.

Added immediate desktop-file drop/picker uploads into the captured current folder, per-file queue/progress/errors, UTF-8 names, a configurable 1 GiB default cap and two server upload slots. Used descriptor-anchored no-symlink traversal, viewed-folder identity checks, private partial files, session rechecks and atomic non-overwriting publication/cleanup. No filesystem sudo grant or new dependency is needed. Directory drops, overwrite/delete/rename/move, preview and upload resume remain outside this version.

Updated all nine wiki pages and README. Twenty file tests passed; the final full regression suite passed 80 tests; syntax checks passed. Browser picker upload and new-folder behavior were verified with exact-byte comparison inside a disposable fixture. Physical desktop drag gestures, large/proxy transfers and crash/network-filesystem acceptance remain unverified. Source revision unavailable (not a Git repository).

## 17 October 2026 — Container management v0.6

Added the authenticated Containers page and unprivileged local Docker/Podman adapter, runtime detection/selector, searchable container/image/volume/network inventories, counts, bounded logs and confirmed start/stop/restart controls. Added the sidebar entry without menu numbers or marketing taglines. No container creation/deletion, image pulls, remote endpoints, Compose/stacks or in-container exec is included.

Updated all nine documentation pages and README. Validation: 93 regression tests passed; 13 container tests rerun after access-message refinement; Python/JavaScript syntax checks passed; simulated browser checks covered runtime switching, four inventory tabs, search, start/stop and logs. Native read-only detection found Docker installed/access denied and Podman absent. Real container modifications and account permission changes were not performed; live lifecycle integration remains unverified. Source revision unavailable in this workspace.

## 18 October 2026 — SMB/NFS Shares v0.7

Added Shares navigation, service installation/status detection, add/edit dialogs, read-only/write settings, managed-folder creation, explicit SMB user or NFS client access, definition enable/disable retaining data, and confirmed service starts. Added no-login share-user provisioning, separate SMB passwords and enable/disable controls. Added a staged root-owned broker/installer with fixed commands, stdin-only credentials, managed-path isolation, optimistic revisions, serialization and configuration rollback. Existing native shares/folders/accounts are not imported; general Linux/AD administration, deletion, dual-protocol folders, quotas and arbitrary exports remain outside scope.

Updated README and all nine local documentation pages. Validation: 121 regression cases passed including 28 share cases; Python/JavaScript/installer syntax checks passed. Browser fixture verified SMB add, NFS edit/disable, user enable/disable and form layout; screenshots reviewed. Read-only host detection found required Samba/NFS tools/units and the share helper absent. No real accounts, groups, services, shares, exports or host permissions changed. Deployment, native client interoperability and backup/restore remain unverified. Source revision unavailable.

## 19 October 2026 — GitHub/systemd installer

Added standalone `deploy/install.sh` for public-GitHub deployment on Debian/Ubuntu and Fedora/RHEL-family systemd hosts: explicit account/ref/options, read-only plan/unit output, native prerequisites, commit-resolved bounded source extraction, non-root final-path virtualenv, private stable configuration, generated loopback Gunicorn service, enable/start/health checks, exclusive installer lock and core backup/rollback attempts. Optional flags install narrow helpers and SMB/NFS packages; SMB config gets a validated managed include and separate-password policy. Skipped helper flags do not revoke or update previous grants. Native packages and optional setup are outside core rollback.

Added 12 offline installer checks; full suite passed 133 tests. Bash syntax/plan and generated systemd directive verification (placeholder executable) passed. Updated README and eight affected wiki pages; API routes are unchanged. No installer was executed against the host, no repository was published/downloaded through it, and live installation, native distro/package integration, PAM login and rollback remain unverified. Source revision unavailable.

## 20 October 2026 — GitHub source repository

Initialized project Git history on `main` and configured `https://github.com/deanralph/DriftOS.git` as origin. Updated README and installer documentation to use the real repository instead of owner placeholders. Credential files (`api.json`, `.env`), virtual environments, downloaded Node dependencies and Python caches are excluded from the initial source upload. A filename-only credential-pattern scan found no matching private-key/GitHub/OpenAI credential patterns in candidate source. This check is not a guarantee that arbitrary sensitive data cannot exist. Prior 19 October regression record remains 133 passing tests; this documentation/repository change does not execute a server install.

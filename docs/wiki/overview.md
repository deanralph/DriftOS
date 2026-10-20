# DriftOS

DriftOS is a Linux server management application for the server owner. The implemented first version provides a PAM login screen and authenticated overview with live processor percentage, core/thread counts, frequency, load averages, RAM use/availability, root storage, mounted filesystems, free space, hostname, OS/kernel and uptime. Sampling occurs every five seconds while the dashboard is open; Refresh requests an immediate sample. Stale data is labelled when requests fail.

An authenticated interactive terminal is implemented at `/terminal`: connect/disconnect, new shells, keyboard input, ANSI rendering, command history, Ctrl+C/Ctrl+D and automatic PTY resizing. Commands execute directly on the local host with the signed-in account’s normal permissions. One terminal per login, four across the single worker. Idle timeout is 15 minutes without keyboard input; the login expires after one hour. Signing out revokes the login and closes its shell. The Applications library is available for curated tools; no dedicated reboot or remote-server connector exists.

Source: `/home/dean/Projects/DriftOS`. Local entry: `http://127.0.0.1:8090`. Health: `/health`. Requires Linux, Python 3, libpam, an eligible local non-root account and installed requirements. Reads the machine running the process; container deployment would report its visible environment rather than reliably describe the host.

Design reference: `/home/dean/Projects/Driftstream/styleguide.html` and `css/driftstream.css`. The shared v0.2.0 stylesheet is copied unchanged to `static/driftstream.css`; app-specific CSS is separate.

## Firewall manager (v0.3)

The authenticated `/firewall` page detects installed UFW, firewalld, nftables and iptables command-line tools. It reports the selected manager's active/inactive/unknown state, defaults, explicit allowed/limited/blocked/other entries and raw manager output. UFW and firewalld support an on/off switch using existing rules; standalone nftables/iptables reports are read-only. Detection prefers an active high-level manager, then an installed high-level manager, then a readable active kernel ruleset. Multiple active high-level managers or unknown peer state prevent switching.

Privileged reports/control require a one-time root-owned helper installation and narrowly scoped sudo authorization. This setup has not been applied to the development host. UFW is installed here, but its live status/rules cannot be confirmed by DriftOS yet; the switch stays disabled and status is Unknown until administrator setup. No host firewall rules or state were changed during implementation. The terminal heading and disconnected view were simplified to remove promotional copy.

## App library (v0.4)

The authenticated `/apps` library offers six tools: btop, htop, tmux, rsync, OpenSSH server and Samba. It shows OS/package-manager detection, package-database installed state and version, search/status filters, and installation progress/logs. Open terminal links are provided for installed command-line tools; they do not automatically execute the displayed command.

Native manager selection uses `/etc/os-release` via Python's `freedesktop_os_release()`: Debian/Ubuntu family → apt (`apt-get`), Fedora/RHEL family → dnf (including dnf5 binary fallback), then yum when dnf is absent; Arch family → pacman. It checks executable presence and does not choose a foreign manager solely because it exists in PATH. Other OS families are currently unsupported.

Installation requires the separate root-owned apps helper described in Deployment. It accepts only curated app IDs and verified native managers. Jobs persist on disk and run outside the web process. Installation does not configure SMB shares or firewall rules; distribution package scripts may start SSH/Samba services. No actual package installation or apps-helper setup was performed in this task. Read-only inspection on the development host identified Omarchy/Arch with pacman, four installed catalogue packages and two missing ones.

## File explorer (v0.5)

The authenticated Files page opens in the running Linux account's home and browses readable directories within `DRIFTOS_FILES_ROOT` (default `/`). It shows folders/files, sizes, modification times and permissions, with breadcrumbs, Up/Home, a path field, per-page filtering, hidden-file visibility and pagination. It also creates folders and downloads regular files as attachments.

Dropping desktop files into the open folder starts a sequential upload queue automatically; selecting files via Upload files uses the same automatic queue. Each file retains the destination captured when it was added, even if the browser navigates elsewhere. Progress and per-file errors are shown. Existing names are never overwritten, symlinks are not followed, and successful uploads appear only after receiving the complete file. Default per-file limit is 1 GiB. Folder/directory drops, delete, move, rename, editing and resumable uploads are not implemented.

Files runs directly as the authenticated same non-root process account and requires no sudo/helper setup. It does not bypass ordinary Linux permissions. Shared menu numbering was removed from every item, including the new Files entry, and the obsolete mobile rule that would hide unnumbered labels was removed.

## Container management (v0.6)

The authenticated `/containers` page detects local Docker and Podman, distinguishes installed/unreachable/connected runtimes and offers a runtime selector. It lists all containers (including stopped), images, volumes and networks, with search, refresh, container counts, ports/status/networks and a bounded log viewer. Existing containers can be started, stopped and restarted after browser confirmation.

This first version manages existing local resources. Container creation, image pulls, deletion/pruning, Compose/stacks, Podman pods, per-container metrics and remote endpoints are not implemented. Docker was installed but denied access for the running account during verification; Podman was absent. Simulated data was used for successful management UI checks. No real containers were changed.

## SMB/NFS shares and share users (v0.7)

The authenticated `/shares` page reports local SMB/NFS server installation and systemd status, adds/edits managed shares, sets read-only/read-write access, enables/disables definitions without deleting data, and offers confirmed service starts. SMB user administration creates dedicated no-login system accounts, provisions/resets separate SMB passwords and enables/disables SMB logins. It does not administer general Linux logins, sudo access, arbitrary existing accounts or AD/domain users.

All managed folders are direct children of `/srv/driftos-shares`; existing folders and external definitions are not adopted/imported or listed. SMB shares are exported as `ds_<name>` with selected `ds_u_<user>` logins. NFS uses explicit IPv4/IPv6 IP/CIDR client allowlists and squashes client identities to UID 65534 plus the dedicated share group. SMB passwords do not apply to NFS. Shares are protocol-specific, not dual-protocol folders. There are no delete/rename/quotas/ACL-editor controls. Managed state records the last confirmed application actions; external native user changes are not reconciled automatically.

The web process remains non-root. A staged, root-owned helper and narrow sudoers rule provide the administrative operations after explicit deployment setup. No real shares/users/services were changed during development. Host inspection on 18 October 2026 found neither required Samba/NFS tools nor a supported service unit or the new helper; real client mount/login verification is pending provisioning.

## Native server installer

`deploy/install.sh` installs from a public GitHub repository on Debian/Ubuntu and Fedora/RHEL-family systemd servers. It installs native Python/PAM/build prerequisites, resolves a branch/tag to a commit (or uses a full commit SHA), downloads/extracts source with bounded archive validation, builds a fresh virtualenv as an existing non-root account, generates private configuration and a single-worker/twelve-thread Gunicorn unit, enables/starts it and checks `/health`. Default access is a localhost listener through an SSH tunnel. The default install grants no new helper permissions; explicit flags select helper grants and sharing packages/configuration.

Source repository: [deanralph/DriftOS](https://github.com/deanralph/DriftOS). Installer examples use this repository and the `main` branch; substitute the server account, or select a reviewed commit SHA. Private repositories, Arch automatic setup, HTTPS/reverse-proxy provisioning, account creation/password setup and Docker/Podman provisioning are not supported by the installer. It has offline/syntax validation but has not been executed as a privileged installer on a server.

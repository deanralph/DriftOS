# Usage & examples

1. Open `http://127.0.0.1:8090` on the machine running DriftOS.
2. Sign in using the configured Linux username and existing Linux password. The default username is the account running the process.
3. Review CPU usage/core counts/load, RAM usage/available memory, root storage and mounted volume capacity/usage/free space.
4. Use Refresh for an immediate sample; otherwise metrics refresh every five seconds.
5. Sign out from the top bar.

Sizes use binary units (KiB, MiB, GiB, TiB). CPU usage samples a 0.2-second interval; load averages are the OS's 1/5/15-minute values. Memory used is total minus available, so reclaimable cache is treated as available. Root storage describes `/`; other mounted filesystems appear in the volume table. Mount rows can share the same backing device and are not summed as independent disks. Inaccessible mounts are omitted. Unmounted disks and SMART health are not provided.

A disconnected banner means the last values may be stale. An expired session sends you back to login. Five login attempts in five minutes block further attempts until the rolling window clears; successful attempts also count. Applications and Terminal are available from the sidebar.

## Interactive terminal

1. Sign in, choose **Terminal**, then **Connect terminal**. Merely opening the page does not start a shell.
2. Run normal commands such as `pwd`, `whoami`, `df -h` or `top`. They run as your signed-in Linux account with its normal permissions and configured shell.
3. Use arrow keys for shell history, Tab completion, Ctrl+C to interrupt and Ctrl+D or `exit` to end the shell. Ctrl+C is handled by the PTY's foreground process group.
4. Resize the browser; the terminal sends its columns/rows to the PTY. Large paste input is split and paced; pastes above the browser's input queue limit are rejected with a message.
5. **Clear view** clears the current visible buffer without executing `clear` or deleting history. **Disconnect** ends the shell and retains displayed output. **New terminal** replaces that view with a fresh shell in your home directory.

Only one terminal can be open for a given login, including across tabs. Another independent login can open a separate shell, up to four globally. There is no automatic reconnection or session persistence across navigation. Closing/leaving the page ends the socket and initiates cleanup. An outage may delay detection until WebSocket/TCP liveness detects it; reload/sign in again if connection fails. Never assume disconnect rolled back a command. Idle timeout tracks keyboard input, so a long-running command without keyboard interaction also ends after 15 minutes.

The terminal canvas is fitted to an unpadded inner container; the surrounding stage supplies spacing and clips rendering above the status bar. The sidebar keeps navigation and its version label without promotional text.

## Firewall

1. Sign in and choose **Firewall**. The page checks installed tools, chooses a manager and reads status/rules.
2. Check Active/Inactive/Unknown, default policies, rule directions/sources, and the expandable full report. Unknown means inspection failed or lacks privileges; it does not mean off. Installed tools may be frontends for the same kernel firewall and are not counted as separate protection layers.
3. Entry counts summarize explicit allow/limit, deny/drop/reject and other rules. They do not count allowed/blocked ports or packets. LIMIT is conditional. Firewalld named services, rich rules, active policy objects, interfaces and sources require reading the full report for context. Inactive UFW rules are labelled saved rather than live.
4. When privileges are missing, the page shows the one-time administrator setup command to run in a server terminal. After that setup (also described in Deployment), use the switch to enable/disable the existing UFW or firewalld configuration. The page disables controls during the request and reads the resulting state back. It does not edit individual rules.
5. Use Refresh to rescan. A stale revision, failed request or timeout requires a fresh report before another switch operation. There is no automatic retry or background polling of firewall reports.

UFW/firewalld conflicts, an unreadable peer manager, incomplete status, or firewalld cleanup-on-exit disabled/unreadable make the switch unavailable. Standalone nftables/iptables are detected and read-only. Their raw reports do not provide a safe disable/restore mechanism in this version. iptables covers the filter table for both address families. A stopped manager does not prove every kernel, container, cloud or router filter has disappeared. The page explains its report scope.

The terminal no longer displays the requested tagline; its initial heading and status now describe connection state directly. New firewall views use functional labels without promotional taglines.

## App library

1. Open **Applications**. Review detected OS and native manager plus the installed-count summary. Only six curated tools are listed; this is not a full repository catalogue.
2. Filter by tool/category text or Installed / Not installed. Each card shows the mapped package and installed version when known. Unknown status is not treated as a missing package.
3. If setup is required, run the command shown in a server terminal with administrator privileges and Refresh. This grants only the reviewed app helper's operations and does not itself install packages.
4. Select **Install** on a missing tool. The page submits one background job and displays status/output. Other install controls are disabled while a job is queued/running or needs review. You can leave the page and return to see the persistent job. Refresh after connection errors before retrying; submission is never automatically retried.
5. On success, the worker verifies package-database state and the card becomes Installed. CLI cards show a usage command and link to Terminal; that link opens the shell page without automatically running anything.

OpenSSH means the SSH **server**, not merely the SSH client. Samba is the SMB server; installation alone does not create shares/users. Package scripts may start server services according to the distro's normal policy, and configured firewall rules still determine access. This version does not expose SSH/SMB service switches, share management, updates or uninstall controls.

Pacman uses the current sync database and may fail when mirrors or metadata are stale; complete normal native system maintenance first. Missing packages/repositories and package lock conflicts appear as failed jobs with output. DriftOS never adds EPEL/AUR/third-party repositories or silently upgrades the entire Arch system.

## Files and desktop uploads

1. Open **Files**. Home opens the account's home; Up, breadcrumbs and the path field navigate folders. With a custom root, paths are relative to that root. Symlink rows are marked and not navigable.
2. Open the destination folder, then drag files from the desktop onto the file list. Receipt starts automatically; there is no separate submit step. Upload files also accepts multiple selected files and starts immediately. Directory drops are rejected with a message; select/drop individual files instead.
3. Follow each file's queued/uploading/Uploaded/Failed state. Each queued file retains the displayed destination from selection/drop time even if you navigate to another folder. Up to 100 pending files can be queued, processed sequentially in this browser. The server permits two simultaneous uploads across sessions.
4. The list refreshes after uploads into the currently displayed folder. Existing names produce an error without replacement. The queue does not retry errors automatically. Check the destination before retrying a lost connection. Clear finished removes only completed/failed queue rows, never host files.
5. Use New folder to create a child folder. Use Download on regular files. Filter this page matches only the current page of entries; Show hidden files reloads the listing. Read-only/unwritable folders disable upload and new-folder buttons.

Listings are folders-first/name-sorted, 100 entries per page by default. The backend accepts page sizes up to 250 and scans at most 10,000 visible entries; it reports that cap and skipped unreadable entries. Hidden files are off initially; internal upload partials never appear. Filenames are preserved, including UTF-8, but slashes/backslashes, dot traversal, control characters, names longer than 255 UTF-8 bytes and reserved temp names are rejected. Downloads are binary attachments, including HTML files; there is no inline preview/editor.

Menu items now show names/icons without numbering. Files needs no administrator setup beyond the existing Linux account permissions.

## Containers

1. Sign in and choose **Containers** in the sidebar. Detection reports each runtime as connected, unavailable or not installed.
2. Choose a connected Docker/Podman runtime. Containers includes stopped containers and shows running/other-state counts; Images, Volumes and Networks provide separate read-only inventories.
3. Search filters the current inventory. Refresh probes runtime connectivity again and reloads the active inventory; updates are manual, not periodic.
4. Use Start for created/stopped/exited containers or Stop/Restart for running containers. Confirm the named container and runtime in the dialog. Controls are unavailable while an operation runs. Other states offer logs only.
5. Logs shows a snapshot of the last 200 lines, capped at 64 KiB. It is not a live stream; stdout/stderr are grouped. Close the viewer or select Logs again to refresh it.

Permission failures and unreachable runtimes are reported distinctly from an empty inventory. Timeouts are not retried automatically: refresh and check the actual state before deciding to retry. Login expiry returns to sign-in on API access. There is currently no deployment wizard, Compose/stack management, resource editor, deletion, prune, image pull or in-container exec UI; the existing Terminal page remains a host shell.

## Shares and share users

Open **Shares** after signing in. SMB/NFS cards show installed tools and supported systemd service status. An administrator setup panel appears when the helper is missing or the Samba managed include needs linking. Existing non-DriftOS shares/accounts are not imported or listed.

For SMB, first choose **Add user**, enter a short name plus matching 12–128 character SMB passwords, then save. A user named `alex` receives login `ds_u_alex`; its system account has no interactive shell, no created home and no Linux password set by DriftOS. **Set password** changes the separate native SMB password. **Disable/Enable** controls future SMB logins after confirmation; established sessions may need to disconnect. Pending users need Set password before they can be selected for a share. General Linux users, sudo permissions and AD/domain accounts are outside this page.

Choose **Add share**, enter a short name, select SMB or NFS and read-only/read-write access (read-only is the default). Folder `/srv/driftos-shares/<name>` is created automatically; existing folders are not adopted. SMB requires one or more provisioned share users and publishes `ds_<name>`. NFS requires comma-separated client IPs or CIDR networks, for example `192.168.1.0/24, 192.168.1.42`; these are illustrative, not discovered host networks. All NFS client identities are squashed to UID 65534 plus the share group, so this release does not preserve client POSIX identities or enforce SMB passwords on NFS.

**Edit** changes access, selected SMB users/NFS clients and enabled status. Names and protocols are immutable. Clearing **Enable share definition** removes the generated definition after Save without deleting its files or metadata. The Definition column reports the managed definition, not proof of an active client connection. Service state is separate. Saving reloads an already-active server; if inactive, choose **Start service** and review the confirmation. Service start can activate external native shares as well. DriftOS does not configure the firewall or boot enablement.

Illustrative connections after service/firewall provisioning (replace placeholders):

```text
SMB Windows: \\<SERVER_IP>\ds_documents
SMB macOS: smb://<SERVER_IP>/ds_documents
SMB login: ds_u_alex
NFS export: <SERVER_IP>:/srv/driftos-shares/backups
```

For an NFS test mount, use the native client's mount command and a disposable mount directory, with explicit intended NFS version/options and permission to mount. Mount/network interoperability is not verified on this host. Refresh is manual. If state changed elsewhere, the API rejects the old revision; close the form, refresh and review before resubmitting. Password fields clear on submit/error/close; re-enter after an error. Do not retry an unconfirmed mutation without checking current native state.

## Install from GitHub

Use `deploy/install.sh` on a supported systemd server, selecting the existing Linux account you will use to sign in. Preview `--plan`, select the desired helper/sharing flags, then install with sudo. The download-and-run example is in Deployment; it uses `deanralph/DriftOS` on `main`; select a reviewed commit SHA when pinning a deployment. The account needs an existing Linux password; the installer does not create credentials.

Default runtime access is through an SSH tunnel from your computer to server loopback port 8090. The script prints the tunnel command, service/log commands, resolved commit and private backup location. A successful health check is followed by real sign-in and feature acceptance on the server. To update, rerun with the intended ref, same user and appropriate helper options. `--helpers none` skips setup without revoking existing permissions; `--sharing` explicitly opts into native package/configuration changes. Services can start through native package scripts. See Data & recovery before rolling back or removing old backups.

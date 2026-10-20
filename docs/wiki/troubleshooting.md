# Operations & troubleshooting

Logs go to the process stdout/stderr; Gunicorn can be supervised by the host's chosen process manager. No metrics history, alerts or monitoring agent is installed. Passwords are not intentionally logged; do not enable request body tracing.

| Symptom | Diagnosis / remediation |
| --- | --- |
| Sign-in rejected | Confirm configured username matches process owner, root is not allowed, host PAM service exists and account/password are valid. Inspect host authentication logs privately. Do not weaken PAM or run web server as root. |
| Too many attempts | Wait five minutes; limit is global for the allowed account and can affect legitimate users. |
| Session lost on restart | Process-local login leases reset on restart; sign in again. Provision a stable private `DRIFTOS_SECRET_KEY` for signing, but it does not preserve leases. |
| Repeated login redirect behind TLS | Verify HTTPS cookie setting, proxy scheme and browser cookie policy. |
| Stale metrics | Check server process, browser connection and `/health`; metrics failure returns 503. |
| Missing volumes | Only visible mounted filesystems are enumerated; permissions and containers limit visibility. |
| CPU frequency missing | Host/kernel may not expose it; UI omits frequency. |
| Address already in use | Stop the old development process or select a different Gunicorn bind port. |

The default PAM service is host `login`; policies may include delays, lockout or interactive requirements. DriftOS only supplies username/password and cannot complete MFA. Throttling, server-side login revocation and terminal slots are process-local capabilities, not distributed infrastructure. Run one worker and validate real host authentication before deployment.

## Terminal issues

| Symptom | Diagnosis / remediation |
| --- | --- |
| Connect fails / 401 | Login may have expired or the service restarted; reload and sign in again. Old signed cookies cannot recreate a revoked lease. |
| WebSocket 403 | Set `DRIFTOS_ORIGIN` to the exact browser origin behind a proxy; preserve Origin and WebSocket upgrade headers. Do not disable origin checks. |
| Account shell unavailable | Run as the authenticated non-root account; verify passwd shell path/executable, home-directory access and PTY availability. Root or another UID is refused. |
| Already open terminal | Disconnect the other tab using the same login; each login permits one terminal. |
| All slots in use | Four live terminals already exist; disconnect an unused login's terminal. |
| Shell ends after 15 minutes | Keyboard inactivity limit includes long-running commands with no keyboard input. |
| Proxy drops the connection | Check HTTP/1.1 upgrade support, 25-second ping handling and proxy idle timeout; proxy deployment remains unverified. |
| Layout stale or missing controls after source edits | Restart the service (templates are cached outside debug mode), then reload the browser so HTML and JS match. |
| Detached process remains | Commands which create a new session or start managed services can survive terminal cleanup. Inspect account processes; do not assume rollback. |

The application does not log keystrokes or terminal transcripts; host audit/PAM logs and shell startup/history behavior are separate. Do not add command/body logging to debug a sensitive terminal session. Inline styles are allowed only on `/terminal` for xterm; scripts remain locally served and self-only.

## Firewall manager

| Symptom | Diagnosis / action |
| --- | --- |
| UFW detected, status Unknown | Live status needs administrator privileges; complete the one-time helper setup in Deployment. An active `ufw.service` alone is not proof of current filtering. |
| Switch disabled | Check access notice, `can_toggle`, unknown/conflicting managers and raw report. Standalone nftables/iptables is read-only. |
| Setup done but still unavailable | Check installed helper/root-owned parents, no writable/symlink paths, correct sudoers account and `sudo -n -- /usr/local/libexec/driftos-firewall report`. Do not paste private reports publicly. |
| Changed state / conflict | Another operation or administrator changed the report; Refresh and inspect before trying again. |
| Timeout / connection lost after switching | The change might have applied. Use a local console/independent access path and read actual state; do not repeatedly submit the toggle. |
| firewalld cannot be stopped safely | CleanupOnExit is disabled/unreadable, so stopping the daemon may leave rules. Native configuration review is required; DriftOS does not change that setting. |
| No explicit entries but traffic blocked | Inspect defaults, firewalld active policy objects/rich rules, external kernel/container/cloud/router filters and interface/source bindings. Counts are not a port reachability test. |

UFW's persistent boot state and firewalld's runtime service state have different semantics, documented in Deployment. The manager does not install firewall tools, add management-port exceptions or provide automatic lockout rollback. Privileged integration is pending on this development host; no rules or state were changed during development.

## App library

| Symptom | Diagnosis / action |
| --- | --- |
| Unsupported OS / manager | Check `/etc/os-release` ID/ID_LIKE and native executable. Supported families are Debian/Ubuntu, Fedora/RHEL and Arch. A foreign manager alone is not selected. |
| Installed state Unknown | Package query timed out, the native database/tool is unavailable or returned an unrecognized error. Refresh and inspect with native read-only tools. Installation is refused while status is unknown. |
| Install disabled before setup | Run the reviewed `install-apps-helper.sh` command shown in Applications as the process account, then Refresh. This is separate from firewall setup. |
| Repository/package not found | Review the job output and enabled repositories. btop or another tool may not exist in this release's enabled repos. No automatic repository/bootstrap/key changes are made. |
| Pacman download/metadata error | Complete normal Arch host maintenance independently. DriftOS does not run `-Sy` or perform a full system upgrade. |
| Another job / package DB lock | Wait for the current transaction. Native package managers also have their own locks; do not delete them blindly. |
| Job Unknown | Check native package state and worker/package processes; retain/move the root-owned unresolved record only after administrator review. See Data & recovery. |
| Browser/app restarted | Reopen Applications and inspect persistent recent jobs; detached installations continue independently. Do not resubmit until checked. |
| SSH/SMB installed but unusable | Installed does not mean configured/listening/reachable. Review native service status, configuration, users/shares and firewall policy. Service controls are outside this version. |

Package operations can take as long as the native installer needs; the worker is not cancelled on logout/browser disconnect. A full machine shutdown can still interrupt a transaction. Job history has no automatic cleanup. Do not share actual installation logs publicly; URL credential redaction is best-effort, not a guarantee every sensitive value is removed.

## File explorer

| Symptom | Diagnosis / action |
| --- | --- |
| Upload/New folder disabled | Wait for the folder listing to finish, or Refresh after a navigation error. The destination may lack write/search permission or be read-only. No sudo elevation is used. |
| Access denied / symlink folder | Files follows no symlinks. Navigate to a real directory inside the configured root that the account can access. |
| Same name already exists | Existing files, directories and symlinks are preserved. Choose a different source filename or manage the existing file separately. |
| Destination changed | The directory identity differs from the viewed folder. Refresh before uploading; queued files retain their original destination. |
| Upload too large / HTTP 413 | Compare the configured per-file limit with the proxy body limit. Ordinary form requests still have an 8 KiB cap. |
| Busy / 429 | Two uploads are already active; wait before manually resubmitting. Each browser normally sends one queued file at a time. |
| No entry after an error | Partial uploads are not published; refresh the destination. A complete file can exist after a late connection failure, so inspect before retrying. |
| Unsupported publication / 501 | The filesystem supports neither non-overwriting rename nor the safe hard-link fallback. Use another compatible destination; overwriting is not used as a workaround. |
| Missing filenames | Check hidden-file visibility, per-page filter, pagination, access permissions and the 10,000-entry scan cap. Upload partials always stay hidden. |
| Drop did nothing / folder dropped | Drop individual files onto the file list, or use Upload files. Folder-tree upload is not implemented. |

No automatic retry, resume, antivirus/content scanning or deletion API is provided. File byte contents are not intentionally logged; normal web access logs can include requested paths. Treat real host filenames and download URLs as private administrative information. After a hard crash, inspect potential orphaned private temp files only once active uploads have stopped (Data & recovery).

## Container management

- **Access denied:** verify the DriftOS service account can access the selected local runtime. Docker socket access is powerful; follow the intended host policy, then restart the service/account context after membership changes. DriftOS never invokes sudo or changes socket permissions.
- **Runtime unavailable:** start/check the local daemon for Docker; confirm the account's rootless socket if one exists. A present rootless socket takes priority over `/var/run/docker.sock`, including when stale. Podman uses local account storage and `--remote=false`; it does not use a remote connection.
- **No containers:** check the selected runtime/account. Rootless Podman and Docker system/rootless stores are separate. An access error should display an unavailable report, not a successful zero count.
- **Operation failed:** container may have disappeared or native state may reject the action. Refresh and check its native state. A timeout can occur after the daemon accepted the command; never blindly repeat it.
- **No logs:** the workload may not emit stdout/stderr, or its logging driver may not support native retrieval. Only the last 200 lines/64 KiB are returned, grouped by stdout/stderr, with no live following.
- **Large inventory/unsupported format:** reports reject more than 4 MiB or unrecognized JSON. Check native CLI compatibility and use native tooling for larger inventories. Read-only image/volume/network tables do not provide resource modification.

There is no persistent audit/job history for container commands. Native daemon logs and container logs remain the primary diagnostics. Successful Docker/Podman lifecycle integration on this host is pending account/runtime access configuration.

## SMB/NFS shares

- **Administrator setup:** run the reviewed share-helper installer for the actual non-root DriftOS account. It does not install server packages or start services. Installed broker copies must be updated separately when source changes.
- **Not installed / no service:** install the native Samba/NFS server package. The page needs systemd and supports SMB `smb`/`smbd`, NFS `nfs-server`/`nfs-kernel-server`. Other service managers/containers require native configuration outside this page.
- **SMB include needs configuration:** back up and edit the main Samba file, appending a global include for `/etc/samba/driftos-shares.conf`; validate `testparm -s`. Main configuration is not created automatically. Domains and non-local passdb backends are rejected. Password changes also require effective `unix password sync = no` to keep Linux passwords separate.
- **No shares listed:** only managed records are listed. Without helper access they are unavailable; existing unmanaged native shares are never imported. Do not assume an empty table proves no server exports exist.
- **SMB user denied:** use the `ds_u_` login, check enabled/pending state and the selected users for `ds_` share name. Set password recovers pending users; reconnect established sessions after access changes. Existing non-managed Linux/domain users are not eligible. Native changes are not automatically reconciled into metadata.
- **NFS denied / write fails:** verify the client CIDR, firewall, service state and read-only setting; NFS does not authenticate SMB users. Clients are squashed to UID 65534 and the per-share group, so native file ownership matters. SELinux/AppArmor, filesystem labeling, mount options and network policy may require distribution-specific administration; DriftOS does not disable those protections.
- **Name/path conflict:** existing folders, accounts/groups and external matching export names/paths are not adopted. An early provisioning failure can leave a reserved name; inspect with native tools instead of blindly deleting data or reusing unrelated identities. Managed names/protocols cannot be renamed.
- **Configuration changed / busy:** close the form, refresh and review current settings. A root-only file lock serializes all operations; do not bypass revision checks.
- **Apply/reload failed:** former managed definitions and membership are restored when possible, with a rollback reload attempt. A failed rollback reload, timeout or partial user creation requires checking native service/account state before retrying. Shared folders/data are retained. Use `journalctl -u <DETECTED_UNIT>` and `testparm -s`/native NFS tools; never paste secrets or private client data into public logs.
- **Definition enabled but unreachable:** enabled is metadata/configuration status, not a connection probe. Start the inactive server deliberately, review all native definitions and configure network/firewall/boot policy separately. Starting or reloading may affect external shares. `exportfs -ra` reconciles all configured exports.

No real share server/client integration was executed on this host; provisioning and disposable client acceptance remain required before production use.

## Automated installer

- **Bootstrap 404 / public GitHub failure:** publish `deploy/install.sh` at the exact owner/repo/ref in the URL. The configured source is `deanralph/DriftOS` on `main`; ensure the selected ref contains the installer. Private repositories/authentication are unsupported; branch/tag resolution can also encounter public GitHub API limits. A reviewed full commit SHA skips API resolution. Do not add credentials to URLs.
- **Unsupported OS/Python/systemd:** automatic packages support Debian/Ubuntu and Fedora/RHEL-family hosts, require systemd and Python 3.10+. Use the manual procedure on other systems or provision the appropriate OS/Python first.
- **Missing/no-login account:** select an existing non-root account with an interactive executable shell and valid Linux password. The installer does not provision login credentials. Login is via host PAM, not an application password.
- **Unsafe destination / drop-ins:** earlier user-owned manual installations, symlinks/group/world-writable administrative paths and existing unit drop-ins are refused. Back up and review/migrate them deliberately; do not blindly change ownership of broad system directories or bypass the guard.
- **Another installer / port occupied:** an exclusive lock serializes runs. If DriftOS is not active, port 8090 must be free. Stop a conflicting preview/service; do not kill an unidentified process. Do not delete a live lock to force concurrency.
- **Core health failure:** inspect `journalctl -u driftos`, private backup and rollback output. The installer attempts previous app/unit/environment and service-state restoration, but native packages persist. Disk or file-restore errors can leave the service stopped for manual recovery. A green health response still does not prove PAM/WebSocket/client interoperability.
- **Optional setup failed:** core DriftOS remains installed after its health checkpoint. Helper/package steps may be partial. Check existing grants, packages and native configuration before retrying. SMB must be standalone/local; existing main configuration is backed up, and a failed syntax check restores it. Package scripts may already have started daemons.
- **Update retains old helper behavior:** omitted flags do not update or remove privileged copies. Repeat the reviewed helper flags when corresponding source changes. Backend source rollback also needs matching installed privileged copies.
- **Tunnel login fails after an HTTPS deployment:** installer preserves private environment settings, including Secure cookies and origin. Continue using the intended HTTPS origin or deliberately reconfigure the deployment; do not assume an update resets it to first-install HTTP.

Backups contain private configuration and accumulate under `/var/backups/driftos`. Review retention manually. Actual server deployment and rollback remain unverified; source is hosted at `https://github.com/deanralph/DriftOS`.

### Unsafe administrative directory: /var/backups

The initial installer required `/var/backups` to already exist, so minimal server images could trigger this error before package/application installation. The corrected installer validates the existing parent and creates the absent directory root-owned mode 0755. Download and rerun the current script from `main`. If the directory already exists and the error remains, inspect it with `sudo stat -c '%A %a %U:%G %n' /var /var/backups` and check for symlinks; unsafe existing paths are intentionally still rejected. Do not use blanket permission/ownership changes to suppress the check.

## LAN port 8090

If a client cannot connect, check `systemctl status driftos`, the generated unit's `--bind 0.0.0.0:8090`, server-local `/health`, the actual server LAN IPv4 address and the client source subnet. `--lan-cidr` must cover the address seen by the server; VPN/CGNAT subnets need explicit overrides if outside RFC1918. Check native UFW/firewalld and any nftables/cloud/router policies. No active supported manager means the installer did not configure rules. Multiple managers or unknown UFW status stop automatic rule additions after core installation.

Login redirects or terminal Origin failures after switching from HTTPS may indicate stale settings: `--lan` resets Secure cookies and clears the saved origin, then restarts the app. Existing browser cookies/logins are invalidated by service restarts; sign in again. LAN mode is IPv4 HTTP only. A source-scoped allow rule is additive and does not remove earlier broad allows or higher-priority deny policies. Returning to loopback does not revoke prior rules; review native configuration deliberately.

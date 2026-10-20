# Data, backup & recovery

There is no SQL database, schema migration or persistent metrics history. File uploads are stored directly in the selected host folder, not in a separate application upload database. Metrics are sampled from the running Linux environment. Sessions use signed browser cookies (HttpOnly, SameSite Strict) and a server-side in-memory login lease with an absolute one-hour lifetime. Cookies contain username, CSRF token, random login ID and session timing, not passwords. Login attempt timestamps and leases reset on restart. Logout revokes the lease, denies copied cookies and ends its active terminal. Key rotation and process restart invalidate logins.

Persistent configuration consists of source, requirements, optional deployment secrets and host PAM policy. `.venv`, Python caches and in-memory samples are disposable. `api.json` is a private WikiStream credential, not app state; it is excluded from Git/image context and must remain mode 600.

Back up source and private service environment separately using normal host backup tools. Do not copy secrets to wiki pages. For recovery, restore source/configuration, recreate `.venv`, install requirements and run the verification commands. Check `/health`, login with the configured user and confirm metrics. No restore drill or remote deployment has been performed; no project backup operation should replace the whole WikiStream workspace.

## Shell state and cleanup

Terminal output is not recorded by DriftOS. The browser retains up to 2,000 lines of scrollback until a new terminal, navigation or page reload; Clear view clears the displayed terminal view. A normal interactive shell may write command history (for example `~/.bash_history`) and commands may create files or change the host. These are real persistent account/host changes and require normal host backups; ending a shell does not undo them.

Disconnect, socket loss, logout, login expiry or keyboard-idle timeout triggers termination and then forced cleanup of processes still in that PTY's POSIX session, including foreground/background job-control groups. Deliberately daemonized processes that create a separate session can outlive the shell, as can operations started through an external service manager. No guarantee of command rollback or cleanup after a hard server crash exists. On recovery, inspect remaining account processes and validate their purpose before stopping them. No persistent terminal reconnect, transcript export or shell history deletion endpoint is provided.

## Firewall state and recovery

DriftOS stores no firewall database or rule history. The firewall tools own their persistent configuration (UFW under `/etc/ufw` with defaults in `/etc/default/ufw`; firewalld under `/etc/firewalld`, subject to the host's actual package configuration). The installed helper and sudoers grant are separate persistent host configuration. `/run/driftos-firewall.lock` is a temporary coordination file, not a backup.

UFW switching may persist across boots; firewalld service start/stop is runtime only. DriftOS does not snapshot or restore rule sets, add access exceptions, flush arbitrary nftables tables, or automatically roll back a change. Connection loss/timeouts can leave the requested change applied even if the browser did not receive confirmation; refresh/read host state before retrying. From a local console, inspect `sudo ufw status verbose` or `sudo firewall-cmd --state` and the full report, then use the native tool and known-good configuration to recover. The correct recovery action depends on the existing access policy; none was executed or validated in this task.

Reports may contain private addresses/interfaces and are served only to authenticated users with no-store headers. They are not intentionally persisted by DriftOS. Back up native firewall configuration consistently through host administration procedures before live changes. No firewall backup/restore drill has been performed.

## Packages and installation jobs

Installed packages and their dependencies/configuration are persistent host state owned by the native package manager. They survive DriftOS restarts and helper removal. Package scripts may also create service accounts, keys and configuration. DriftOS offers no uninstall, downgrade, rollback, package-database repair or service-configuration API in this version.

Root-owned job records are JSON files at `/var/lib/driftos/app-jobs/<32-hex-id>.json` (0600 within 0700 directories). Fields include ID, app/package/manager, state, creation/update Unix seconds, message, bounded log tail, optional installed version and internal process identity. Writes replace records atomically; there is no SQL migration. `/run/driftos-apps.lock` is temporary coordination state, retained by the worker while the native transaction runs. Jobs continue across web-process restarts/sign-out, but a machine reboot can interrupt them. Reports return the ten most recent records; records have no automatic retention/deletion policy.

Read job state through the authenticated UI or native helper after setup. The log tail redacts obvious HTTP URL user/password credentials and token-like query values, but operational output should still be treated as private. Do not post real logs/configuration publicly. The broker does not inherit the web service's credentials/environment.

A missing worker/start-time mismatch or stale queued record is reported Unknown. Unknown/running/queued jobs block new catalogue installs, including after a web restart; there is no automatic retry or cancellation. Inspect the actual package manager/processes and package database from a local administration terminal. Do not blindly remove native database locks or kill a running transaction. After confirming the operation ended and handling native recovery, an administrator may back up and move the unresolved job JSON outside the job directory to acknowledge it; retain that record privately rather than deleting it blindly. No such recovery or live-install test has been executed here.

Back up native package/configuration state using the host's established tools and copy job records only when the worker is idle or using a consistent snapshot. Rebuild DriftOS's venv independently of system-package state. Restoring app source/job files does not undo package/service changes.

## Explorer files and upload recovery

Uploads are real host files in the selected directory and survive app restart, logout and source/venv replacement. New directories are also persistent host state. Back them up with the host's normal consistent filesystem backup procedure; DriftOS supplies no version history, restore, delete or overwrite operation. Existing files are preserved even on duplicate upload attempts. File batches are independent transactions: one failed upload does not roll back earlier successes.

Incomplete uploads normally leave no destination file; the private same-directory partial file is removed on stream errors, size violations or session revocation. A hard process/machine crash can leave `.driftos-upload-*.part` files. They remain excluded from Files listings/downloads, including Show hidden files. Inspect them from a trusted native terminal after confirming no uploads are active; only then remove confirmed orphaned partials. Do not run wildcard deletion against a folder while uploads may be running.

A connection/storage failure after atomic publication can leave a complete file even if the browser missed the success response. Refresh and inspect the destination before retrying. No automatic retry, duplicate suffix or overwrite is attempted. Upload queue state is browser memory and is lost on reload/navigation away; downloads/listings are not consistent backup snapshots of concurrently changing files. No crash-recovery, network-share durability or disk-quota restore drill was performed.

## Container state and recovery

DriftOS does not maintain a container database or persist inventory/log copies. Docker/Podman retain their own containers, images, networks, volumes and configuration outside this project. Their actual data-root/storage paths and application backup procedures must be discovered on the target deployment; they were not verified here. Backing up DriftOS source does not back up container volumes or hosted application data.

Start/stop/restart changes native container state and can interrupt hosted services. Stop/restart use a 10-second grace period; the runtime may terminate the workload after that period according to its semantics. Existing container configuration is reused. There are no create/delete/prune controls in this release. An ordinary stop can be followed by Start; review logs and native service dependencies if it fails. For ambiguous timeouts refresh the native state before retrying. Temporary CLI output files close on command completion/error; no audit history or persistent management job queue is implemented. Container logs can contain sensitive application data and are visible only to authenticated DriftOS sessions.

## Share state, data and recovery

| Location | Contents / ownership |
| --- | --- |
| `/var/lib/driftos/shares/state.json` | Root-only metadata for managed shares and user lifecycle flags; no passwords |
| `/var/lib/driftos/shares/state.previous.json` | Previous metadata snapshot, root-only; not a full backup |
| `/var/lib/driftos/shares/lock` | Root-only serialization lock |
| `/etc/samba/driftos-shares.conf` | Generated SMB sections, root-owned 0644 |
| `/etc/exports.d/driftos.exports` | Generated NFS definitions, root-owned 0644 |
| `/srv/driftos-shares/<name>` | Persistent shared data, root-owned directory / dedicated `ds_s_<name>` group, initially 2770 |
| Native Linux/Samba databases | `ds_u_<name>` no-login system users, private primary groups, dedicated share-group memberships and native SMB password hashes |

Source rollback/recreation does not remove these host files, accounts, groups or shared data. Disabling a definition stops generating it but preserves the directory, files, group and metadata. Disabling SMB access does not remove data, Linux accounts or share assignments and may leave established client sessions connected. No delete, rename, automated retention, recursive chmod/chown or adoption of existing folders is implemented.

A new account is recorded disabled/pending after Linux creation and before Samba provisioning. If password provisioning fails, refresh and use Set password on the pending account, then enable it as needed. A new share is recorded disabled after its group/folder is created, before applying configuration; refresh/edit that record if activation fails. If failure occurs before metadata can be saved, a reserved group/account/directory can remain without a record. Do not adopt/reuse an unrelated name to bypass that conflict; inspect with native tools and repair or choose a new name. Password changes and service-start failures can have partial native effects; refresh/review before retrying.

For consistent backups, prevent administrative writes through DriftOS and native tools and quiesce clients/applications writing share data. Back up metadata, managed files, main Samba configuration, other exports, native account/group identifiers, native Samba private credential database using distribution-supported methods, and data with numeric ownership/permissions/ACLs. Discover Samba's actual private database path on the installed server; none was present to verify here. Protect credential backups as secrets. A source backup alone is insufficient, and `state.previous.json` cannot restore native passwords, UID/GID assignments or files.

Restore on a disposable host first: restore consistent metadata/configuration and native identity/credential state with matching numeric IDs, then shared data and ownership; validate `testparm -s` and native export definitions, inspect client allowlists, start/reload the intended native services, and test allowed/denied clients plus read-only/write behavior before directing production clients to it. Do not blindly replace metadata alone while services are active. Recover a failed apply by comparing the saved managed file, `state.json`/previous snapshot and service journal; rollback reload errors require manual native-state verification. Backup/restore, real mounts and reboot persistence were not tested during this implementation.

## Installer backups and partial-failure recovery

Each installer run creates `/var/backups/driftos/install-*` mode 0700. When present, prior `/opt/driftos` is copied as `application`, the previous systemd unit as `driftos.service`, and the private environment as `driftos.env`. Optional SMB configuration is saved as `smb.conf` before modification. Core failure may retain the failed app as `failed-application`. Backups can contain signing secrets or account-readable application files and must remain private; there is no automatic retention/deletion. `/opt/driftos/INSTALLATION` records the selected repository/ref/resolved commit. `/run/driftos-installer/lock` is ephemeral and does not need backup.

Before the core health checkpoint, a failed install attempts to stop the new service, restore the old source/virtualenv at its original absolute `/opt/driftos` path, restore unit/environment, reload systemd and restore prior active/enabled state. File-restoration failure leaves the service stopped with a manual-recovery message. Success of this failure path on a real server has not been tested. Native prerequisite packages are never rolled back. A failed first install can leave prerequisite packages, empty configuration directories and private backup material.

After core health success, optional helper/package/Samba operations are outside rollback: an error can leave a working core service, installed helper grants, newly installed packages and partially completed optional setup. Inspect the printed error and native state before rerunning. A failed Samba config syntax check restores its previous main-file bytes, but this is not a transaction over package scripts, native daemon state or helper permissions. Skipped options do not revoke already-installed helpers. Persistent shares, users/groups, app jobs, native firewall state, Docker/Podman data and user files outside `/opt/driftos` are not included in installer app rollback or the copied source backup.

For manual rollback, stop DriftOS and select the correct private backup; preserve any failed/new installation separately, restore `application` to `/opt/driftos` (not a different path, because virtualenv shebangs are absolute), restore the matching unit/environment, run `systemctl daemon-reload`, and restore intended boot/start state. Compare installed helper copies with the restored backend version before granting functionality. Validate `/health`, PAM login and terminal operation, then relevant native features using disposable data. Do not restore configuration or a partial metadata backup alone as a substitute for the feature-specific consistent recovery procedures above. Actual installation rollback, Samba integration and full backup restoration remain unverified.

## LAN-mode settings and rule retention

The existing private environment backup includes HTTPS/origin settings before `--lan` clears the origin and sets `DRIFTOS_HTTPS=0`. Core failure restores the former private environment together with source/unit. Once health passes, additive UFW/firewalld rules are outside rollback and may be partially applied if a later step fails. Repeating or switching to loopback does not automatically revoke them. Review native current/persistent rules before removing individual DriftOS rules; preserve unrelated firewall state. The installer does not back up or restore the complete firewall. No actual firewall modification/recovery was tested here.

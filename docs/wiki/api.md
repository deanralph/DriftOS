# API & integrations

DriftOS uses browser sessions, not API bearer tokens. No CORS integration or external automation token is implemented.

| Method / path | Behavior |
| --- | --- |
| `GET /health` | Public 200 JSON `{"status":"ok"}` |
| `GET /login` | Login HTML; initializes CSRF session token |
| `POST /login` | Form fields `username`, `password`, `csrf`; success 302 to `/`, invalid credentials 401 HTML, throttled 429 HTML |
| `GET /` | Authenticated dashboard HTML; anonymous 302 to login |
| `GET /terminal` | Authenticated terminal HTML; anonymous/expired 302 to login |
| `GET /ws/terminal` | Authenticated WebSocket upgrade; invalid session 401, wrong/missing Origin 403 |
| `GET /api/stats` | Authenticated metrics JSON; anonymous 401 JSON, collection failure 503 JSON |
| `POST /logout` | Form field `csrf`; clears session and redirects 302 to login |
| `GET /static/<path>` | Public CSS and JS assets |

All POSTs require the session CSRF token; invalid/missing token gives 403 JSON. Request bodies default to 8192 bytes (413 when exceeded); the raw file-upload endpoint has its own configurable limit described below. Login admits only `DRIFTOS_USER` and rejects root. No passwords are returned. Unknown routes return 404; wrong methods return 405.

`/api/stats` fields: `hostname`, `os`, `kernel` strings; `uptime` seconds; `sampled_at` Unix seconds; `cpu` object with `percent`, physical `cores` (nullable), logical `threads`, `frequency` MHz (nullable), `load` array of 1/5/15-minute averages; `memory` object with byte counts `total`, `used`, `available`, `swap_used`, `swap_total`, and `percent`; `drives` array with `device`, `mount`, `filesystem`, byte counts `total`, `used`, `free`, and `percent`. Collecting CPU blocks a request for about 0.2 seconds. No history/pagination or write operations exist.

Public example, from the server:

```bash
curl --fail http://127.0.0.1:8090/health
```

Authenticated example: sign in through the browser, then open `/api/stats` in that browser. Do not put Linux passwords into command-line arguments or examples.

## Terminal WebSocket protocol

Connect to the same-origin `ws://HOST/ws/terminal` or `wss://HOST/ws/terminal` with the signed session cookie and exact browser Origin. A live server-side login lease is required. No tokens are accepted in query strings. Within five seconds, send a JSON text opening frame:

```json
{"type":"open","csrf":"<token from authenticated page>","cols":80,"rows":24}
```

The server checks CSRF, dimensions, account identity, session expiry and capacity before creating a shell. Columns must be integers 2–500, rows integers 2–200 (booleans are invalid). One active connection per login and four total per worker.

| Client type | Fields / behavior |
| --- | --- |
| `open` | First frame only: `csrf`, `cols`, `rows` |
| `input` | `data`: UTF-8 string, at most 4096 encoded bytes per frame; at most 65536 pending bytes |
| `resize` | Integer `cols`, `rows` in the ranges above |
| `close` | End the shell and close socket |

| Server type | Fields / behavior |
| --- | --- |
| `ready` | PTY subprocess created; shell startup output follows |
| `output` | `data`: decoded terminal text, including ANSI sequences |
| `exit` | `message`: shell exited, explicit close, login ended or idle timeout |
| `error` | `message`: invalid token/frame/size, duplicate terminal, slots exhausted or unavailable shell; socket closes |

Binary or malformed/unsupported messages are rejected. WebSocket frame limit is 32768 bytes, separate from the ordinary 8192-byte HTTP body limit and the file-upload limit. Oversized frames are closed by the WebSocket transport (1009). The service sends pings every 25 seconds. Keyboard inactivity of 900 seconds or absolute login expiry ends the shell. Output uses incremental UTF-8 decoding and retains no server transcript. Login/logout revocation is process-local, so deployment must use exactly one worker. Shell-start success is not a new PAM login/session; it uses the already authenticated account and the existing process UID, without privilege escalation.

## Firewall endpoints

| Method / path | Authentication and behavior |
| --- | --- |
| `GET /firewall` | Authenticated HTML; otherwise 302 to login |
| `GET /api/firewall` | Authenticated JSON report; 401 if login missing/expired, 409 if helper operation is busy |
| `POST /api/firewall` | Authenticated form fields `csrf`, `backend` (`ufw` or `firewalld`), `enabled` (`true` or `false`), `revision` (64 lowercase hex characters) |

The report includes `backend`, `name`, `installed` tool names, `detected_managers` with observed active states, `active` (boolean or null), `sampled_at` Unix seconds, `rules`, `policies`, `raw`, `scope`, `error`, `conflict`, `can_toggle`, `revision`, and `privileged`. Unconfigured access also supplies `setup_required`, a shell-quoted `setup_command` for the process account, and `access_note`. A successful HTTP report does not imply its `active` value is known; inspect `active`/`error`/`can_toggle`.

Rule objects contain `action`, `direction`, `target`, `source`, `details`, `scope` (`live` or `saved`). Policy objects contain `direction` and `action`. Complex firewalld policy objects remain in the raw report. Counts are computed by the UI, not backend promises about reachable ports.

A successful POST returns the freshly read report, HTTP 200. Invalid inputs: 400. Missing/invalid CSRF or a root/mismatched process account: 403. Changed report hash, unsafe/unsupported manager or conflicting operation: 409. Missing helper permissions, timeout, execution error or unconfirmed change: 503 with `error`; some uncertain results also include a `report`. The report hash detects changes to the selected manager/status/output and supported control state. The root helper rechecks before executing a fixed command. Writes are never retried automatically and timeouts must be reconciled by a new read.

The normal signed browser session is the only API authentication; there is no root password/token transmission, arbitrary command endpoint or firewall rule-editing API. Helper invocation uses noninteractive sudo. Report requests can take up to roughly 40 seconds on helper timeout; browser requests time out at 45 seconds. There is no guarantee a timed-out change failed.

## App-library endpoints

| Method / path | Behavior |
| --- | --- |
| `GET /apps` | Authenticated library HTML, otherwise 302 to login |
| `GET /api/apps` | Authenticated OS/manager/catalogue report, otherwise 401 |
| `POST /api/apps/install` | CSRF-protected form fields `app` (curated ID), `manager` (detected native manager) and `csrf`; success 202 queued job |
| `GET /api/apps/jobs/<job_id>` | Authenticated status/output for a 32-character lowercase hex job ID |

Report fields: `os`, `os_id`, `os_like`, `manager` (apt/dnf/yum/pacman or null), `available_managers`, `error`, `sampled_at`, `apps`, `jobs`, `privileged`, `can_install`; unconfigured helper also supplies `setup_required` and shell-quoted `setup_command`. Tool entries contain `id`, `name`, `category`, `icon`, `description`, mapped `package`, tri-state `installed`, `version`, `command` and optional server-side-effect `note`.

Curated IDs are `btop`, `htop`, `tmux`, `rsync`, `openssh`, `samba`. Arbitrary packages/options are not accepted. Selection is rechecked on submission. Write routes require the signed-in non-root process account in addition to the session/CSRF checks.

Job fields include `id`, `app`, `package`, `manager`, `state`, `message`, `created_at`, `updated_at`, `log`, optional `version`. API job reads hide internal process IDs/start identity. Queued submission responses may include only the initial public job fields. States: queued, running, succeeded, failed, unknown. Output is a bounded 65,536-character tail and is updated at most about twice per second while output flows. The UI polls active jobs every two seconds; there is no WebSocket/install cancellation endpoint.

Errors: unauthenticated 401; bad CSRF/account 403; malformed app/manager/job ID 400; missing job 404; changed manager, unknown/already-installed package state or existing transaction/review job 409; helper/setup/submission error 503. A request timeout does not prove job submission failed: refresh recent jobs before retrying. Native package failures are represented in a successfully read job's state/log, not as failed HTTP polling. No package transaction is automatically killed because an HTTP request ended.

## File explorer endpoints

All endpoints require a live login belonging to the same non-root process account. `/files` redirects anonymous users to login; file APIs return 401. Permission failures return 403. Other errors include invalid path/name 400, missing path 404, existing name/changed destination 409, size violation 413, wrong upload type 415, busy upload slots 429, unsupported safe-publication filesystem 501, storage/quota exhaustion 507, or unconfirmed filesystem error 503. HTTP errors on these API paths return JSON with `error`.

| Method / path | Input and success |
| --- | --- |
| `GET /files` | Explorer HTML, initially account home within configured root |
| `GET /api/files` | Query `path` (default `/`), `hidden=1`, `offset` (default 0), `limit` (default 100, maximum 250); 200 listing |
| `POST /api/files/folders` | Form `csrf`, `path`, `name`, `folder_id`; 201 child folder |
| `POST /api/files/upload` | Raw octet-stream body and headers below; 201 uploaded file metadata |
| `GET /api/files/download` | Query `path`; 200 regular-file attachment, not rendered inline |

Listing fields: virtual `path`, physical `actual_path`, configured `root`, virtual `home`/`parent`, `folder_id`, `writable`, `entries`, `total`, `offset`, `limit`, `next_offset`, `truncated`, `skipped`, `max_upload_bytes`. Entries contain `name`, virtual `path`, `type` (folder/file/link/special), `size` (null except regular files), Unix `modified` and `permissions`. `total` is limited to the supported scan window, not a promise about an arbitrarily large directory. Offsets beyond the current list clamp to the last page.

Upload headers:

```text
Content-Type: application/octet-stream
X-CSRF-Token: <current session token>
X-Folder-Path: <percent-encoded virtual folder path>
X-Folder-Id: <folder_id returned by listing>
X-File-Name: <percent-encoded plain UTF-8 filename>
```

The token is not accepted in a URL; this endpoint reads it from the header before touching the body. Other POSTs keep form CSRF. Upload bytes are bounded by `DRIFTOS_UPLOAD_MAX_MB` (default 1 GiB), independently of the ordinary 8192-byte body cap. Stream size and declared Content-Length are validated when available. Session validity is rechecked before publication. Success fields: `name`, virtual `path`, `size`. Folder creation returns `name` and virtual `path`. Neither write endpoint overwrites an existing name. There is no delete/rename/move, resumable upload, folder-tree upload, inline content preview or sudo filesystem endpoint.

## Containers API (v0.6)

Every route below requires a live authenticated session and the same non-root real/effective Linux process identity as the signed-in account. Responses are JSON; all responses inherit no-store/security headers. Pages use the existing login session; `/containers` redirects unauthenticated users to login. Mutations require form field `csrf` with the session token; arbitrary action strings, shell commands and short/name identifiers are rejected.

| Method | Path | Result |
| --- | --- | --- |
| GET | `/api/containers/runtimes` | `runtimes` array with `id` (`docker`/`podman`), `installed`, `available`, `message`, plus `version` when connected |
| GET | `/api/containers/<runtime>/inventory/<kind>` | `items` array; kind is `containers`, `images`, `volumes` or `networks` |
| GET | `/api/containers/<runtime>/<id>/logs` | `log` text and human-readable `limit` |
| POST | `/api/containers/<runtime>/<id>/<verb>` | Form `csrf`; verb `start`, `stop` or `restart`; returns `message` |

Container fields: `id`, `name`, `image`, `state`, `status`, `ports`, `networks`. Image fields: `id`, `name`, `tag`, `size`, `created`; values depend on native runtime format and unavailable fields show `—`. Volume fields: `name`, `driver`, `scope`. Network fields: `id`, `name`, `driver`, `scope`. IDs for actions/logs must be exactly 64 lowercase hexadecimal characters. Inventories are not paginated and reject CLI output exceeding 4 MiB. Display strings are truncated to 2048 characters. Logs request the last 200 lines, cap combined text at 64 KiB and group stdout/stderr.

Typical errors: 400 invalid runtime/kind/action/ID, 401 expired/missing login, 403 CSRF or process identity rejection, 404 uninstalled runtime, 429 two commands already executing, 503 inaccessible runtime/failed command/unsupported JSON, 504 timeout. Runtime detection can return HTTP 200 with `available:false` per runtime. A timeout does not prove a native mutation failed. Mutations are synchronous, not queued, and are never retried automatically.

Example request paths: `GET /api/containers/docker/inventory/containers`; `POST /api/containers/docker/<FULL_CONTAINER_ID>/stop` with URL-encoded `csrf=<SESSION_CSRF>`. Use an existing authenticated browser session; there is no bearer API authentication in DriftOS. Do not copy or publish session cookies or log data in examples.

## Shares API (v0.7)

`/shares` and every `/api/shares` endpoint require the live PAM-authenticated login lease and the same non-root real/effective process account. All POSTs require URL-encoded form field `csrf`. There is no bearer API authentication. Report and errors inherit no-store/security headers. Framework errors under this API return JSON. Configuration and service mutations additionally require the report's optimistic `revision`; stale state returns 409 before mutation. Names cannot include arbitrary paths or configuration text.

| Method | Path | Fields / response |
| --- | --- | --- |
| GET | `/api/shares` | `privileged`, `shares`, `users`, `services`, `root`, `note`; privileged reports include `revision`; fallback includes `setup_required`, `setup_command` |
| POST | `/api/shares/share` | `revision`, `name`, `protocol` (`smb`/`nfs`), `read_only`, `enabled` (literal `true`/`false`), repeated `users` for SMB or `clients` comma-separated IP/CIDRs for NFS |
| POST | `/api/shares/user` | `revision`, `name`, `action` (`create`, `password`, `enable`, `disable`); `password` required for create/password |
| POST | `/api/shares/start` | `revision`, `protocol` (`smb`/`nfs`); starts a fixed detected service, without boot enablement |

Successful mutations return `message`. Share records contain `name`, `protocol`, `read_only`, `enabled`, `users` (short names), `clients` (normalized CIDRs). User records contain `name`, `account`, `enabled`, `pending`; these are last confirmed managed flags, not an independent live account-database audit. Service records contain `installed`, `service`, `active`; privileged records also include `ready`, and SMB reports `linked` when its tooling/unit is available. `active` concerns the service, while `enabled` concerns a share/account definition. The fallback report's empty managed arrays mean administrator state is unavailable, not proof that the server has no external shares.

Limits: request body 8192 bytes; helper input separately capped at 8192 JSON bytes (Unicode encoding overhead may cause rejection), names 1–20 ASCII lowercase letters/digits/underscore/hyphen starting with a letter, passwords 12–128 characters with no CR/LF/NUL, 64 managed shares/users, 32 selected users per SMB share, 16 unique explicit IP/CIDR clients per NFS share; wildcard/all-host networks are rejected. SMB protocol/name cannot change for an existing share. Arbitrary existing folders/accounts are never adopted. Passwords are supplied only to native SMB provisioning via stdin and never returned/stored by DriftOS; use HTTPS for remote browser traffic.

Errors include 400 invalid input/action, 401 missing/expired login, 403 CSRF/process identity, 404 unmanaged user, 409 stale revision/name conflict/unsupported Samba role or backend/password synchronization/another operation, 413 oversized HTTP body, and 503 missing setup/tools/native operation failure or timeout. Broker stderr and raw native output are not returned. Command timeouts are ambiguous and are not retried. Reports use a root-only lock too and can return busy rather than partially read an ongoing write.

Example shapes, using an existing authenticated browser session and placeholders (never publish real session tokens/passwords):

```text
GET /api/shares
POST /api/shares/share
csrf=<SESSION_CSRF>&revision=<REPORT_REVISION>&name=documents&protocol=smb&read_only=true&enabled=true&users=alex
```

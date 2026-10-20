<!-- WikiStream project setup -->

## This project’s WikiStream settings

Read `wikistream.json` for the authoritative non-secret settings. Use its exact `name`, `slug`, `description`, `documentation_directory` and `url`. Set `WIKISTREAM_URL` to that URL for API commands. Use the agent environment token or read `api.json` as described below; never print credentials. The HTTP default is for the deliberately trusted internal network.

# Project documentation instructions for WikiStream

Import this file into a project's agent instructions. For agents that discover `AGENTS.md`, merge it into the project's existing `AGENTS.md`, or rename this file to `AGENTS.md` when that file does not exist. Preserve the project's other instructions.

This guide describes WikiStream API version 1.1.0, verified against its source on 13 October 2026. Fetch the deployed instance's `/api/openapi.json` if its implementation has changed.

## 1. Configure this project

Fill in these non-secret values when importing the instructions:

| Setting | Value to provide |
| --- | --- |
| Project name | `DriftOS` |
| Stable project slug | `driftos`; e.g. `home-infrastructure` |
| Project description | A short explanation of the purpose and audience |
| Local documentation directory | `docs/wiki/` by default |
| WikiStream base URL | Supply as `WIKISTREAM_URL`, e.g. `http://10.0.0.100:8080` |
| API credential | Environment `WIKISTREAM_API_TOKEN`, or private `api.json` containing `api_key` |

Do not assume NoteFlow's or any other project's numeric IDs. Discover the target project by its stable slug on each new installation. The server's `.env` contains its configured API token, but agents in other projects should receive only that token through their approved environment or secret store; they do not need access to the VM, its `.env`, its database, or its session secret.

Never put passwords, tokens, private keys, connection strings containing credentials, session cookies or sensitive production data into Markdown, screenshots, committed files, example output or logs. Document secret variable names and how to provision them instead. Use placeholders in examples. Preserve TLS certificate verification. Use HTTP only on a deliberately trusted development/network deployment; use HTTPS when the service is available through TLS.

## 2. Documentation responsibilities

### File-based credentials for internal use

When the environment token is unavailable, look for `api.json` in this project's root, then `~/.config/wikistream/api.json`. Do not recursively search other repositories. Read the selected JSON file into the API client's memory; it must be an object with a string `api_key`. A malformed project file is an error, not a reason to silently use another credential. Never use `cat`, print the JSON/token, put the token in a command argument, or include it in tool output. Use file mode 600 and keep `api.json` excluded from Git and image builds; ignore rules do not untrack files already committed.

For example, the file format is `{"api_key": "<YOUR_WIKISTREAM_API_TOKEN>"}`. Enter the real value using a local editor. The WikiStream checkout supplies a Python client that reads the credential directly and makes requests without requiring an exported token:

```bash
python3 /home/dean/Projects/WikiStream/scripts/wikistream_api.py /api/projects
python3 /home/dean/Projects/WikiStream/scripts/wikistream_api.py /api/projects --method POST --body-file /tmp/wiki-project-create.json
```

Run from the project root or pass `--project-dir`. Adjust the checkout path if needed. The URL comes from `--url`, the environment, `wikistream.json`, then `http://10.0.0.100:8080`. The client supports JSON GET/POST/PATCH and binary downloads to redirected output; multipart uploads still need a client that reads the same file into memory. Redirects are refused and writes are not retried. The curl examples below require an environment token; prefer this Python client when using the file option.

For initial development and every material project change, inspect the actual repository, configuration and tests, then maintain the project's documentation in the same task. Keep the documentation sufficient for another person to understand, deploy, operate, use, test and recover the project without reconstructing this conversation.

Update the affected local Markdown pages and publish them to the matching WikiStream project through the API when the configured service and credentials are available. This instruction authorizes maintaining this project's documentation within the current work. Do not alter another project's entries or WikiStream infrastructure as part of documenting this project.

Use stable page slugs. Prefer the pages below, combining small topics when useful. Mark genuinely inapplicable sections as such with a short reason rather than inventing infrastructure or capabilities.

| Page slug | Suggested title | Sidebar section | Required content |
| --- | --- | --- | --- |
| `overview` | Overview | Getting started | Purpose, audience, implemented features, important limitations, source location, entry URLs, current status and prerequisites |
| `architecture` | Architecture & tools | Infrastructure | Component/request flow, directory map, languages/frameworks, actual versions, external services, dependencies, ports, protocols and design decisions |
| `deployment` | Deployment & configuration | Infrastructure | Clean-machine setup, build/start/stop commands, production versus development, Docker/Compose configuration, required environment variables, secret provisioning, network/TLS setup, health checks and updates |
| `data-and-recovery` | Data, backup & recovery | Infrastructure | Schema and storage locations, persistent volumes, ownership, migrations, retention/deletion behavior, consistent backups, restore procedures, rollback and recovery validation |
| `usage` | Usage & examples | Getting started | Core user workflows, realistic examples, input/output, UI behaviors, common errors, screenshots/diagrams where helpful |
| `api` | API & integrations | Reference | The project's own API, authentication/permissions, every supported endpoint, request/response fields, limits, errors and runnable integration examples; mark absent if it has no API |
| `verification` | Tests & verification | Verification | Exact commands, prerequisites, isolated fixtures, expected results, positive/negative cases, acceptance checks and actual execution records |
| `troubleshooting` | Operations & troubleshooting | Operations | Logs/metrics, monitoring, symptoms and diagnosis, safe remediation, common failures and known operational limitations |
| `changelog` | Documentation change log | Reference | Date, source revision when available, material behavior/infrastructure changes, affected pages and verification result |

### Writing requirements

- Describe implemented behavior; distinguish planned features, assumptions and unverified deployment details.
- Obtain dependencies/versions from the repository and environment actually checked. Do not guess a hostname, VM address, port, database or authentication scheme.
- Provide commands with the correct working directory and prerequisites. Include configuration required to make a clean setup work.
- Explain persistent state separately from source code and temporary files. Record what survives container recreation and what would delete it.
- For risky operational commands, state what they modify and how to recover. Test migrations and restore procedures on a disposable instance when possible.
- Use fenced code blocks with language names, Markdown tables for references, and relative WikiStream media links for uploaded images.
- Include sample output or expected responses that match the implementation. Label illustrative output and placeholders clearly.
- For every recorded test run, state date, source revision if known, environment, command, result and relevant limitations. Never describe a test as passed unless it was executed successfully.
- Keep expected verification procedures separate from actual execution records. A successful unit suite does not prove VM deployment, network access, backup recovery or MySQL behavior.
- Preserve useful manually written wiki content, including deployment observations and previous test results. Merge the changed sections instead of replacing unrelated information.
- Read existing revisions when they help understand a disputed change. Do not restore an old version automatically.

### Completion checklist

1. Inspect the change and identify affected pages.
2. Update local Markdown and check commands, links, examples and factual statements.
3. Run relevant project tests; record actual results or the concrete reason they could not run.
4. Find/create this project's WikiStream entry and its missing pages.
5. Read each existing target page before updating; reconcile its content with the local changes.
6. Publish changes with optimistic version checks. Skip unchanged pages to avoid unnecessary revisions.
7. Read each written page back and confirm title, section and Markdown match the intended result. Verify images through their authenticated file endpoint.
8. Report pages updated, validation completed, and anything still unpublished or unverified. If WikiStream is unreachable or credentials are missing, retain the local documentation and report publication as pending; do not claim remote updates succeeded.

## 3. API authentication and conventions

Set the base URL without a trailing `/`. Supply the token through an environment variable or secret store, not a literal in an instruction file:

```bash
export WIKISTREAM_URL='http://10.0.0.100:8080'
# WIKISTREAM_API_TOKEN must already be supplied securely.
: "${WIKISTREAM_URL:?Set the WikiStream base URL}"
: "${WIKISTREAM_API_TOKEN:?Supply the WikiStream API token securely}"
```

Automation requests use this header:

```text
Authorization: Bearer <WIKISTREAM_API_TOKEN>
```

Bearer tokens work on `/api/` paths only. Do not use them on `/`, `/login`, `/logout` or `/media/ID`. Do not put the token in a URL or query parameter. All API routes are authenticated, including reads, search, image downloads and OpenAPI. Only `/health` is public.

JSON mutations require `Content-Type: application/json` and a JSON **object** body. File uploads use `multipart/form-data` with the field `file`; let the HTTP client supply its boundary. Bearer-authenticated requests do not need browser cookies or CSRF tokens. Do not send cookies alongside the token.

IDs for projects/pages/revisions are integers; asset IDs are UUID strings. Timestamps are timezone-aware UTC ISO 8601 strings. JSON responses are objects or arrays, except image downloads, which return binary PNG bytes.

### Reusable curl helper

These examples use Bash, curl supporting `--fail-with-body`, Python 3, and jq. The helper passes the token to curl through stdin rather than as a command-line argument. Do not enable shell tracing or verbose curl logging around credentials. Standard generated WikiStream tokens are hexadecimal; use the token exactly as provisioned.

```bash
ws() {
  printf 'header = "Authorization: Bearer %s"\n' "$WIKISTREAM_API_TOKEN" |
    curl --config - --silent --show-error --fail-with-body \
      --connect-timeout 5 --max-time 60 "$@"
}
```

For an API body containing Markdown, serialize it from a file using a JSON library. Avoid manually interpolating Markdown into shell JSON: quotes, newlines and backticks must be escaped correctly.

## 4. Complete endpoint reference

| Method | Path | Success | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | 200 | Public database/schema readiness |
| GET | `/api/projects` | 200 | All projects with their page metadata |
| POST | `/api/projects` | 201 | Create a project |
| PATCH | `/api/projects/{project_id}` | 200 | Update project name/description |
| POST | `/api/projects/{project_id}/pages` | 201 | Create a Markdown page and revision 1 |
| GET | `/api/pages/{page_id}` | 200 | Read source, rendered HTML and current version |
| PATCH | `/api/pages/{page_id}` | 200 | Update a page and append a revision |
| GET | `/api/pages/{page_id}/revisions` | 200 | Full history, newest version first |
| GET | `/api/search?q={query}` | 200 | Search titles/content across projects |
| POST | `/api/preview` | 200 | Render Markdown without saving |
| POST | `/api/assets` | 201 | Upload a raster image |
| GET | `/api/assets/{asset_id}/file` | 200 | Download PNG bytes using API authentication |
| GET | `/api/openapi.json` | 200 | Fetch the OpenAPI 3.0.3 schema |

There are no API deletion endpoints, project-by-slug endpoint, asset-list endpoint, bulk page-publishing endpoint, or idempotency-key support. Discover projects and page IDs through `/api/projects`. Slugs cannot be changed through PATCH. Pages cannot be moved between projects through this API. Only send documented request fields; other fields are currently ignored.

### GET /health

No token required. Returns `{"status":"ok"}` with HTTP 200 when the database and initial project schema are available, or `{"status":"unavailable"}` with HTTP 503. This does not prove every workflow or image is functioning.

```bash
curl --silent --show-error --fail-with-body "$WIKISTREAM_URL/health"
```

### GET /api/projects

Returns an array in project-ID order. Each project contains:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | integer | Project ID |
| `slug` | string | Stable globally unique slug |
| `name` | string | Display name |
| `description` | string | Project summary |
| `created_at` | string | UTC creation timestamp |
| `pages` | array | Page metadata, ordered by page ID |

Page metadata contains `id`, `project_id`, `slug`, `title`, `section`, `version`, `created_at`, `updated_at`. It does **not** include `content` or `html`; read `/api/pages/ID` for those. There is no pagination in this version.

```bash
ws "$WIKISTREAM_URL/api/projects" > /tmp/wiki-projects.json
PROJECT_SLUG='my-project' # Replace with this project's stable slug.
PROJECT_ID=$(jq -r --arg slug "$PROJECT_SLUG" \
  '.[] | select(.slug == $slug) | .id' /tmp/wiki-projects.json)
```

An empty `PROJECT_ID` means the project has not been created. Never assume seeded numeric IDs or choose a project by display name alone.

### POST /api/projects

| Field | Required | Type / limit | Default |
| --- | --- | --- | --- |
| `name` | Yes | Non-empty string, at most 160 characters | None |
| `slug` | Yes | Non-empty slug, at most 100 characters | None |
| `description` | No | String, at most 5,000 characters | Empty string |

Slugs match `^[a-z0-9]+(-[a-z0-9]+)*$`: lowercase ASCII letters, digits and single hyphens, without leading/trailing hyphens. Project slugs are globally unique.

```bash
ws -X POST "$WIKISTREAM_URL/api/projects" \
  -H 'Content-Type: application/json' \
  --data-binary '{"name":"My project","slug":"my-project","description":"Purpose and scope of this project."}'
```

Returns the project fields listed above, without the `pages` array. Duplicate slug returns 409. If creation times out or returns a duplicate error, re-list projects and locate the exact slug before retrying.

### PATCH /api/projects/{project_id}

Optional fields: `name` and `description`, with the same types/limits as creation. Omitted fields stay unchanged. Returns the project object without `pages`. Missing project returns 404.

```bash
ws -X PATCH "$WIKISTREAM_URL/api/projects/$PROJECT_ID" \
  -H 'Content-Type: application/json' \
  --data-binary '{"description":"Updated, accurate project summary."}'
```

Project edits have no optimistic version field or revision history. Read current metadata first and avoid replacing someone else's description without reconciling it.

### POST /api/projects/{project_id}/pages

| Field | Required | Type / limit | Default |
| --- | --- | --- | --- |
| `title` | Yes | Non-empty string, at most 200 characters | None |
| `slug` | Yes | Same slug syntax as projects, at most 100 characters | None |
| `section` | No | Non-empty string, at most 100 characters | `General` |
| `content` | No | Markdown string, at most 500,000 characters | Empty string |

Page slugs are unique **within a project**. Different projects may each contain `overview`. Creation stores a full revision with version 1.

Example using a local Markdown file:

```bash
python3 - <<'PY' > /tmp/wiki-page-create.json
import json
from pathlib import Path
print(json.dumps({
    'title': 'Overview', 'slug': 'overview', 'section': 'Getting started',
    'content': Path('docs/wiki/overview.md').read_text(encoding='utf-8')
}))
PY
ws -X POST "$WIKISTREAM_URL/api/projects/$PROJECT_ID/pages" \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/wiki-page-create.json > /tmp/wiki-page-created.json
PAGE_ID=$(jq -r '.id' /tmp/wiki-page-created.json)
```

Returns a full page object as described next. Missing project returns 404; duplicate page slug returns 409. JSON must encode real Markdown newlines, not accidental literal `\\n` sequences.

### GET /api/pages/{page_id}

Returns:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | integer | Page ID |
| `project_id` | integer | Parent project ID |
| `slug` | string | Stable per-project slug |
| `title` | string | Page title |
| `section` | string | Sidebar grouping label |
| `content` | string | Original Markdown |
| `version` | integer | Current optimistic concurrency version |
| `created_at` | string | UTC creation timestamp |
| `updated_at` | string | UTC last-save timestamp |
| `html` | string | Sanitised rendered Markdown |

Missing page returns 404. Use `content` as the editable source, not `html`.

```bash
ws "$WIKISTREAM_URL/api/pages/$PAGE_ID" > /tmp/wiki-page-current.json
jq '{id, title, section, version, updated_at}' /tmp/wiki-page-current.json
```

### PATCH /api/pages/{page_id}

Required: `version`, a JSON integer equal to the current page version. Strings, floats and booleans are invalid. Optional: `title`, `section`, `content`, with the same limits as creation. Omitted fields are preserved.

`content` replaces the entire Markdown field; it does not append or patch individual sections. Merge local updates with remote content **before** sending the request. Every successful PATCH increments the version, updates `updated_at` and retains a complete revision, even if the supplied content is unchanged. Skip unchanged writes.

After inspecting `/tmp/wiki-page-current.json` and preparing a reconciled local file:

```bash
python3 - <<'PY' > /tmp/wiki-page-update.json
import json
from pathlib import Path
current = json.loads(Path('/tmp/wiki-page-current.json').read_text())
print(json.dumps({
    'version': current['version'],
    'content': Path('docs/wiki/overview.md').read_text(encoding='utf-8')
}))
PY
ws -X PATCH "$WIKISTREAM_URL/api/pages/$PAGE_ID" \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/wiki-page-update.json > /tmp/wiki-page-saved.json
ws "$WIKISTREAM_URL/api/pages/$PAGE_ID" > /tmp/wiki-page-verified.json
```

Returns the updated full page object. Missing page returns 404. Missing/invalid version returns 400. A stale version returns 409 and leaves the existing page unchanged.

On a stale edit, fetch the latest page, compare it with the earlier source and the intended changes, merge, then submit using the new version. Never defeat the check by simply fetching a new version and attaching it to an unreconciled old draft.

### GET /api/pages/{page_id}/revisions

Returns an array, newest version first. Each revision contains `id` (revision ID), `page_id`, `version`, `title`, `section`, `content` and `created_at`. Revisions do not contain `html`, page slug or `updated_at`.

```bash
ws "$WIKISTREAM_URL/api/pages/$PAGE_ID/revisions"
```

To restore old text, read the **current** page version, select the desired historical content/title/section and PATCH them as a **new** revision after reconciling changes. There is no restore endpoint and no history deletion endpoint.

### GET /api/search?q={query}

Matches literal substrings in titles or Markdown content. The server trims the query and limits it to 200 characters. Empty query returns `[]`; results are limited to 50 without pagination or guaranteed relevance order. Case behavior depends on database collation. Search is workspace-wide, so filter `project_id` when using it for this project.

Each result contains page metadata plus `excerpt`, which is the **first 180 characters** of the Markdown, not necessarily the location of the match. It does not contain full `content` or `html`.

```bash
ws --get "$WIKISTREAM_URL/api/search" --data-urlencode 'q=backup verification'
```

Use the project's page metadata/slug to identify a canonical page; search is a convenience, not a unique lookup.

### POST /api/preview

Accepts `{"content":"Markdown"}` and returns `{"html":"sanitised HTML"}`. `content` is optional (default empty), must be a string and has the same 500,000-character limit. No project, page, asset or revision is created.

```bash
ws -X POST "$WIKISTREAM_URL/api/preview" \
  -H 'Content-Type: application/json' \
  --data-binary '{"content":"## Example\n\n- First step\n- Second step"}'
```

Supported rendering includes headings, lists, fenced code blocks, tables and heading IDs. HTML is sanitised through an allowlist; scripts and event handlers are removed. Do not depend on executable HTML, JavaScript, custom CSS or SVG embedded in pages.

### POST /api/assets

Upload using multipart field `file`. PNG, JPEG, WebP and GIF input is accepted after raster validation. SVG, non-image data and oversized/decompression-bomb images are rejected. Images are re-encoded to PNG with metadata removed; animated images retain their first frame. Do not expect byte-identical original files or animation after upload.

```bash
ws -X POST "$WIKISTREAM_URL/api/assets" \
  -F 'file=@docs/images/architecture.png' > /tmp/wiki-image.json
jq '{id, url, markdown, size}' /tmp/wiki-image.json
```

Response:

```json
{
  "id": "<asset UUID>",
  "url": "/media/<asset UUID>",
  "markdown": "![Image](/media/<asset UUID>)",
  "size": 12345
}
```

`size` is the stored PNG size in bytes. Uploading an image does not create/update a page or associate it with a project. Insert the returned relative media URL in the intended page and save separately. Use meaningful alt text:

```markdown
![Request flow from browser through the application to database storage](/media/<asset UUID>)
```

Place blank lines before/after image Markdown, especially after tables or code blocks. Reuse existing asset URLs for unchanged images. There is no asset deduplication, listing or deletion API; avoid uploading the same image on every documentation run. Keep a non-secret local mapping of image content hashes to returned UUIDs/URLs if useful.

Images are stored persistently on the VM, independently of page revisions. Removing an image reference from Markdown does not delete the asset. Preserve useful historical image references.

### GET /api/assets/{asset_id}/file

Returns the stored image with `Content-Type: image/png`. Use bearer authentication:

```bash
ASSET_ID=$(jq -r '.id' /tmp/wiki-image.json)
ws "$WIKISTREAM_URL/api/assets/$ASSET_ID/file" --output /tmp/wiki-image-verified.png
```

Missing asset returns 404. The corresponding `/media/ID` path is for authenticated browsers, not bearer API clients. A public or signed image URL is not provided.

### GET /api/openapi.json

```bash
ws "$WIKISTREAM_URL/api/openapi.json" > /tmp/wikistream-openapi.json
```

Returns WikiStream's OpenAPI 3.0.3 schema, API version 1.1.0. It is a reference for request shapes and routes; inspect actual responses for the full fields described above. If the deployed interface differs from this guide, use the deployed schema/source to resolve the discrepancy and update these instructions.

## 5. Limits, errors and retries

| Rule | Behavior |
| --- | --- |
| Total request size | At most 10 MiB (10 × 1024 × 1024 bytes), including multipart overhead |
| Stored PNG size | At most 10 MiB after decoding/re-encoding |
| Markdown content | At most 500,000 characters per page or preview |
| Project name / page title | At most 160 / 200 characters |
| Description | At most 5,000 characters |
| Slug / section | At most 100 characters |
| Search | 200-character query; up to 50 results |
| Required textual fields | Must be strings and non-empty after trimming |
| `content` | Preserved verbatim, including whitespace; empty allowed |
| Other writable strings | Trimmed by the server; `description` may be empty |

HTTP errors generally have a JSON object body:

```json
{"error":"Human-readable explanation"}
```

| Status | Meaning | Action |
| --- | --- | --- |
| 400 | Malformed JSON, wrong field type, invalid slug, empty required field, invalid image or missing/invalid version | Correct the request; do not retry unchanged |
| 401 | Missing/invalid token or unauthenticated browser | Check credential provisioning; do not log the token |
| 403 | Browser CSRF failure or cross-origin mutation rejected | Use bearer API authentication for automation; refresh a browser session if relevant |
| 404 | Missing project, page or asset | Refresh discovery and check the ID |
| 409 | Duplicate slug or page version conflict | Discover the existing entry, or fetch/reconcile the current page before resubmitting |
| 413 | Request or stored image too large | Reduce/split content or resize/compress the image |
| 415 | JSON content type missing for a JSON mutation | Send JSON with the correct header |
| 503 | Database/schema unavailable or browser configuration missing | Check public health and service status; retain pending documentation locally |
| 5xx / network timeout | Server/proxy/transport failure | Read remote state before assuming a write failed or repeating it |

A reverse proxy may return a non-JSON error. Parse the HTTP status first; handle unexpected content without printing credentials. For transient read failures, use a small number of retries with backoff.

Do not blindly retry writes. Creation might have succeeded before the response was lost: look up the exact project/page slug. A PATCH might have committed: re-read content/version and history. An image upload might have succeeded, but there is no listing/idempotency API to recover its ID; record that uncertainty before uploading a duplicate. The API currently has no built-in rate limiting or per-project token scopes, so the shared token must be used only for the authorized project and purpose.

## 6. Browser authentication reference

Automation should use bearer authentication. For completeness, the browser routes are:

- `GET /login`: creates a CSRF token in the session and renders the password form.
- `POST /login`: form fields `password` and `csrf`; successful login redirects to `/`. Incorrect password returns 401; invalid CSRF returns 403.
- `GET /`: authenticated workspace HTML, exposing the current CSRF token in `<meta name="csrf-token">`.
- `POST /logout`: requires the session and `X-CSRF-Token` header; returns `{"ok":true}`.
- `/media/{asset_id}`: private image download for signed-in browsers.

Browser sessions are signed, HttpOnly, SameSite=Lax and last 12 hours. Cookie Secure is enabled when configured for HTTPS. Session-authenticated mutations require `X-CSRF-Token`; an Origin header, when present, must match the request host origin. Changing the password or signing secret invalidates existing sessions. Do not extract/share browser credentials or build an automation flow around password login when an API token is available.

## 7. Repeatable publication procedure

1. Resolve the configured URL and environment/file credential without printing the token.
2. GET `/health`, then authenticated GET `/api/projects`.
3. Match this project's slug exactly. Create it only if missing. On duplicate/ambiguous creation, discover it again.
4. For each planned local page, match its stable slug within that project's `pages` array.
5. If missing, create it with title, section and Markdown. If present, GET its full source/version before deciding how to merge.
6. Skip pages already matching the desired title, section and content. For changed pages, submit only documented fields and the version that was read before reconciliation.
7. On 409, re-read and merge; never auto-overwrite unrelated remote changes.
8. Upload new/changed images once, retain their IDs, and embed their relative URLs into the Markdown before saving.
9. GET the page after writing and compare the returned source with the intended source. Download an uploaded image through the API to verify availability.
10. Add a dated change-log entry with source revision and actual validation. Report remote page IDs or workspace links, plus any pending updates.

Normal documentation publishing has no bulk transaction across multiple pages or assets. If publication partially fails, report exactly which writes were verified and resume the remaining pages by their slugs. Keep local documentation available even when the wiki cannot be reached.

## Administrative backup/restore endpoints (API v1.1.0)

These operate on the **whole workspace**, including other projects. Do not use them while publishing this project's documentation. Export or restore only when the human user explicitly requests an administrative backup/recovery task for the workspace.

| Method | Path | Request / response |
| --- | --- | --- |
| GET | `/api/backups/export` | Authenticated logical database + registered-image ZIP |
| POST | `/api/backups/inspect` | Multipart `file`; JSON `created_at`, `sha256`, `format`, `version`, `schema_version`, `counts` (projects/pages/revisions/assets), `image_bytes`; no data changes |
| POST | `/api/backups/restore` | Multipart `file`, `confirm=RESTORE`, matching inspected `sha256`; replaces the workspace, first creating a recovery ZIP |
| GET | `/api/backups/recovery` | Array of `filename`, `size` (bytes), `modified_at` (Unix seconds) |
| GET | `/api/backups/recovery/FILENAME` | Recovery ZIP download; filename must be returned by the server |

Restore JSON includes `restored`, `counts`, `sha256`, `recovery_backup` and `sign_in_required`. It preserves project/page/asset IDs, versions and history; browser sessions are invalidated. Passwords/API token stay unchanged. The recovery copy is persistent in the server's image volume but must be downloaded separately for off-VM safety. No merge, deletion/retention endpoint, SQL dump import or automatic retry is supported. Use the standalone `scripts/wikistream_backup.py` from another machine (Python 3, standard library only):

```bash
python3 wikistream_backup.py --url "$WIKISTREAM_URL" --token-file ./api.json backup --output ./wiki-backup.zip
python3 wikistream_backup.py --url "$WIKISTREAM_URL" --token-file ./api.json inspect ./wiki-backup.zip
# Only for an explicitly authorized replacement/recovery task:
python3 wikistream_backup.py --url "$WIKISTREAM_URL" --token-file ./api.json restore ./wiki-backup.zip --confirm RESTORE
```

The client can instead read WIKISTREAM_API_TOKEN, then project/shared api.json files when --token-file is absent. It refuses existing output paths and downloads atomically/private (mode 0600 on Unix). Credentials and configuration are excluded from archives. Archive version/schema is 1; default compressed/expanded limit is 256 MiB (`WIKISTREAM_MAX_BACKUP_MB`). Body overhead and proxy limits can cause 413. Invalid archive fields/images/paths or missing confirmation return 400; mismatched SHA-256 or recovery-copy failure return 409. Maintenance can return 503.

Do not infer a failed restore from a network timeout: read the workspace/recovery list before retrying. Valid ZIP checksums detect corruption, not a trustworthy archive origin. Direct database/file writes or multi-host stores outside the shared upload volume must be quiesced independently.

<!-- End WikiStream project setup -->

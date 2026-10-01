# API Jouskaio.me

One modular REST API for my apps, services and personal infrastructure. Each capability is a
**module** mounted under `/api/v1/<module>` and enabled by configuration.

| Module | Status | Purpose |
|---|---|---|
| `notes_sync` | ✅ Available | Brings my **Notability** notes into my **Obsidian** vault, with local handwriting OCR |
| `orchestrator` | 🔜 Planned | Infrastructure orchestration: Proxmox, Docker, Synology, media |

The interactive documentation (Swagger) is served at `/api/v1/docs` when
`JOUSKAIO_ENABLE_DOCS=true`. It documents every route, every response code and every field.

- [Quick start](#quick-start)
- [API reference](#api-reference)
- [Configuration](#configuration)
- [Module: notes_sync](#module-notes_sync)
- [Development](#development)
- [Architecture](#architecture)
- [Git workflow and CI/CD](#git-workflow-and-cicd)
- [Roadmap](#roadmap)

## Quick start

```bash
uv sync
cp .env.example .env                 # then set JOUSKAIO_API_TOKEN: openssl rand -hex 32
uv run uvicorn jouskaio_api.main:create_app --factory
```

```bash
TOKEN=...                            # the value of JOUSKAIO_API_TOKEN
curl localhost:8000/api/v1/health
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/health/modules
```

With Docker: `docker compose up -d --build`, after setting the host paths and `PUID`/`PGID`
in `.env` (see [Configuration](#configuration)).

## API reference

### Conventions

- **Versioning**: every route lives under `/api/v1`, documentation included. A breaking change
  goes to `/api/v2`, served side by side until clients have moved.
- **Naming**: `/api/v1/<module>/<resources>[/{id}]`, module and resources in plural kebab-case.
- **Authentication**: every route except `GET /api/v1/health` requires
  `Authorization: Bearer <token>`, the token being `JOUSKAIO_API_TOKEN`.
- **Long actions** answer `202 Accepted` with a resource to poll until its `status` is
  `succeeded` or `failed`.
- **Tracing**: every response carries `X-Request-ID` (the one you sent if valid, otherwise a
  generated one). It appears in every log line of the request.

### Errors

Every error has the same body:

```json
{ "error": "NotFoundError", "detail": "Run 3f2a9c not found" }
```

| Code | `error` | When |
|---|---|---|
| `400` | domain error type | The request is invalid for a business reason |
| `401` | `AuthenticationError` | Missing or wrong Bearer token (with `WWW-Authenticate: Bearer`) |
| `404` | `NotFoundError` | The resource does not exist |
| `409` | `ConflictError` | The request conflicts with the current state (e.g. a run is already in progress) |
| `422` | (FastAPI format) | Malformed request: `{"detail": [{"loc": ..., "msg": ...}]}` |
| `500` | `InternalServerError` | Unexpected error; internal details are only in the server logs |
| `502` | `ExternalServiceError` | A dependency (external tool, file system, remote service) failed |
| `503` | (health report) | `GET /health/modules` only: at least one module is unhealthy |

### Routes

| Method | Route | Responses | Purpose |
|---|---|---|---|
| GET | `/api/v1/health` | `200` | Public liveness probe, used by the Docker healthcheck |
| GET | `/api/v1/health/modules` | `200`, `401`, `503` | Health of each enabled module |
| GET | `/api/v1/docs` | `200` | Swagger UI (only if `JOUSKAIO_ENABLE_DOCS=true`, `404` otherwise) |
| GET | `/api/v1/openapi.json` | `200` | OpenAPI schema (same condition) |
| POST | `/api/v1/notes-sync/runs` | `202`, `401`, `409` | Start a synchronisation run |
| GET | `/api/v1/notes-sync/runs` | `200`, `401` | Recent runs, newest first |
| GET | `/api/v1/notes-sync/runs/{job_id}` | `200`, `401`, `404` | One run and its per-note report |
| GET | `/api/v1/notes-sync/notes` | `200`, `401` | Notes already synchronised |

Every route can also answer `500`. When docs are enabled, `GET /` redirects to `/api/v1/docs`.

## Configuration

Settings come from environment variables or a `.env` file. Module settings are only read when
the module is enabled.

### Core

| Variable | Default | Description |
|---|---|---|
| `JOUSKAIO_API_TOKEN` | *(required)* | Bearer token, at least 32 characters (`openssl rand -hex 32`) |
| `JOUSKAIO_ENABLED_MODULES` | `notes_sync` | Comma-separated modules to mount; an unknown name stops the startup |
| `JOUSKAIO_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`; logs are JSON lines |
| `JOUSKAIO_ENABLE_DOCS` | `false` | Serve Swagger and the OpenAPI schema; keep `false` in production |

### notes_sync

Paths are the ones **inside** the container; the defaults match the Docker volumes.

| Variable | Default | Description |
|---|---|---|
| `JOUSKAIO_NOTES_SYNC_INBOX_DIR` | `/inbox` | Folder receiving Notability's Auto-Backup exports |
| `JOUSKAIO_NOTES_SYNC_VAULT_DIR` | `/vault` | Root of the Obsidian vault |
| `JOUSKAIO_NOTES_SYNC_NOTES_SUBDIR` | `Notability` | Vault folder receiving the Markdown notes |
| `JOUSKAIO_NOTES_SYNC_ATTACHMENTS_SUBDIR` | `Attachments/Notability` | Vault folder receiving the original PDFs |
| `JOUSKAIO_NOTES_SYNC_STATE_FILE` | `/data/notes_sync_state.json` | What was already synchronised |
| `JOUSKAIO_NOTES_SYNC_MIN_FILE_AGE_SECONDS` | `10` | Files modified more recently are left for the next run (upload in progress) |
| `JOUSKAIO_NOTES_SYNC_EXTRACT_PDF_TEXT` | `true` | Copy the typed text of PDFs into the notes (needs `pdftotext`) |
| `JOUSKAIO_NOTES_SYNC_OCR_ENGINE` | `none` | `none` or `kraken` (handwriting OCR, see below) |
| `JOUSKAIO_NOTES_SYNC_OCR_MODEL` | `/data/models/McCATMuS_nfd_nofix_V1.mlmodel` | Kraken recognition model |
| `JOUSKAIO_NOTES_SYNC_OCR_DPI` | `200` | Page rendering resolution (100 to 400): lower is faster, less accurate |
| `JOUSKAIO_NOTES_SYNC_OCR_MAX_PAGES` | `30` | Pages recognised per note at most |
| `JOUSKAIO_NOTES_SYNC_OCR_THREADS` | `1` | CPU threads used by the OCR |

### Docker Compose

| Variable | Description |
|---|---|
| `NOTES_INBOX_PATH` | Host folder mounted read-only on `/inbox` |
| `OBSIDIAN_VAULT_PATH` | Host vault mounted on `/vault` |
| `DATA_PATH` | Host folder mounted on `/data` (state, OCR model), default `./data` |
| `PUID` / `PGID` | User and group owning the vault on the host |
| `WITH_OCR` | `true` to build the image with the OCR engine (`linux/amd64` only, +1.5 GB) |

## Module: notes_sync

### What works

Notability has **no public API**. The only official, automatable channel is its *Auto-Backup*,
which exports every note to Box, Dropbox, Google Drive, OneDrive or a **WebDAV server**, as
PDF, RTF or `.note` (proprietary). It is a **one-way** backup: deleting a note does not delete
its copy, and iCloud is not available for this mode.

| Direction | Verdict |
|---|---|
| Notability → Obsidian | ✅ Automated through Auto-Backup (PDF or RTF) |
| Obsidian → Notability | ❌ No API and no automatable import (manual import only) |

What the module does with each format (*Settings > Connected Services > Auto-Backup > File
Format* in Notability):

| Format | Result in Obsidian |
|---|---|
| **PDF** (recommended) | PDF copied into the vault and embedded (`![[...]]`), plus its typed text, plus its handwriting when OCR is enabled |
| **RTF** | Converted to Markdown with pandoc, best for typed notes |
| `.note` | Ignored and reported as `unsupported` (undocumented proprietary format) |

### Pipeline

```
iPad (Notability) ──Auto-Backup──▶ WebDAV (Synology) ──folder──▶ /inbox
                                                                  │
                                       POST /api/v1/notes-sync/runs
                                                                  ▼
                               API Jouskaio.me ──▶ /vault (Obsidian)
```

1. On the NAS, enable the *WebDAV Server* package and create a dedicated folder.
2. In Notability, point Auto-Backup to that WebDAV server, format **PDF**.
3. Mount that folder read-only on `/inbox` and the vault on `/vault` (see `compose.yml`).
4. Trigger a run with `POST /api/v1/notes-sync/runs` (manually, from cron, or a scheduled task).

> The iPad must reach the WebDAV server: directly at home, through a VPN (Tailscale,
> WireGuard) elsewhere. Never expose WebDAV or this API directly on the Internet.

### Outcome of each note

A run reports one outcome per file found in the inbox:

| Outcome | Meaning |
|---|---|
| `created` | A new Markdown note was written to the vault |
| `updated` | The note existed; its managed block was regenerated, your own edits outside it are kept |
| `skipped` | Nothing changed since the last run (same content, same processing) |
| `unsupported` | No converter for this format (e.g. `.note`) |
| `conflict` | A file not managed by this module exists at the target path, or its markers were removed; it is left untouched |
| `failed` | The note could not be processed; `detail` says why, the other notes go on |

A run itself is `queued`, then `running`, then `succeeded` (with the report) or `failed` (with
`error`, e.g. the inbox is unreachable). Only one run at a time: a second `POST` gets `409`.

### Guarantees

- **Idempotent**: a SHA-256 per file; an unchanged note is `skipped`. When the processing
  changes (OCR enabled, model changed), existing notes are processed again **once**. When the
  OCR fails on a note, the note is still synchronised, and the OCR is retried on the next run.
- **Your edits are safe**: generated content lives in a block delimited by
  `<!-- notability:begin -->` and `<!-- notability:end -->`. Anything you write outside that
  block survives updates.
- **Never overwrites**: an existing file that is not managed, or has lost its markers, is
  reported as `conflict` and left untouched.
- **Never deletes**: the Notability backup does not, neither does the module.
- **Isolation**: a failing note never stops the others.
- **Confinement**: file names are sanitised and nothing is written outside the vault.
- **Uploads in progress**: files modified less than 10 seconds ago wait for the next run.

Known limitation: if Notability re-exports a PDF whose bytes change without any content change
(metadata), the note is reported as `updated`. Harmless: the managed block is regenerated.

### Handwriting OCR

Optional, **fully local**, CPU only, sized for a small VM. Engine: [Kraken](https://kraken.re)
(research-grade handwritten text recognition) with the
[McCATMuS](https://doi.org/10.5281/zenodo.13788177) model (handwritten, printed and
typewritten text, French, English and 5 other languages, CC BY 4.0).

For each page: render it to an image (pypdfium2), find the text lines (Kraken's bundled `blla`
model), then read each line. The text lands in the note under `## Handwriting (OCR)`, inside the
managed block.

**Enable it**

```bash
scripts/fetch-ocr-model.sh        # downloads the model to $DATA_PATH/models and checks its SHA-256
```

```dotenv
WITH_OCR=true                       # image built with kraken + CPU-only torch
JOUSKAIO_NOTES_SYNC_OCR_ENGINE=kraken
```

Then `docker compose up -d --build`. Without Docker: `uv sync --extra ocr` and
`JOUSKAIO_NOTES_SYNC_OCR_MODEL=./data/models/McCATMuS_nfd_nofix_V1.mlmodel`.

When OCR is requested but cannot work (missing dependencies or model), the API **refuses to
start** with an explicit message rather than silently syncing without OCR.
`GET /api/v1/health/modules` shows the active engine (`ocr=kraken:...`).

**Measured footprint** (1 thread, A4 pages at 200 dpi, Apple Silicon):

| | Value |
|---|---|
| Model loading (first PDF, then kept in memory) | ~10 s, torch import included |
| Per page | ~3 to 5 s |
| Peak memory | ~1.2 GB |
| Docker image | 1.9 GB instead of 0.4 GB |

Expect a small VM to be **3 to 5 times slower** per page. That is fine: runs happen in the
background and each note is processed once. Give the VM **at least 2 GB of RAM**.

**Constraints and limits**

- **x86_64 only**: Kraken depends on `coremltools`, which ships no Linux ARM binaries. The OCR
  image is built for `linux/amd64` only.
- Accuracy depends a lot on the handwriting: try it on a few real notes before relying on it.
- Typed text on a page is read twice (extraction and OCR) and may appear twice.
- Drawings, formulas and arrows are not transcribed (or badly).

## Development

Two processes, each in its own terminal:

```bash
# API with hot reload: restarts on every change in src/ (Swagger on /api/v1/docs)
uv run --extra ocr uvicorn jouskaio_api.main:create_app --factory --reload --reload-dir src
```

```bash
# Tests in watch mode: rerun on every save (< 1 s, the real Kraken test excluded)
uv run --extra ocr ptw . --now --clear -m "not slow"
```

A local `.env` can point the module to `dev/inbox` and `dev/vault` (both ignored by git), with
`JOUSKAIO_ENABLE_DOCS=true` and `JOUSKAIO_NOTES_SYNC_MIN_FILE_AGE_SECONDS=0`. Drop a PDF in
`dev/inbox`, start a run from Swagger (*Authorize* with the token of `.env`, kept across page
reloads), and open the result in `dev/vault`. `uv run pytest` runs everything, `slow` tests
included.

macOS prerequisites: `brew install uv pandoc poppler`.

> **Project inside iCloud Drive** (e.g. `~/Documents`): iCloud flags the virtual environment's
> files as hidden, and Python then ignores its `.pth` files (`ModuleNotFoundError:
> jouskaio_api`). Keep the environment out of the sync with a `.nosync` folder:
> `rm -rf .venv && mkdir .venv.nosync && ln -s .venv.nosync .venv && uv sync --extra ocr`.

## Architecture

```
src/jouskaio_api/
├── main.py                  # create_app(): loads the enabled modules, mounts their routers
├── core/                    # shared foundation, depends on no module
│   ├── config.py            # Settings (JOUSKAIO_*)
│   ├── errors.py            # domain exceptions (translated to HTTP in one place)
│   ├── http.py              # request id, error handlers, documented error responses
│   ├── jobs.py              # long actions: 202 + polling
│   ├── logging_setup.py     # JSON logs
│   ├── module.py            # Module contract + ModuleContext
│   └── security.py          # Bearer authentication
└── modules/
    ├── __init__.py          # module registry
    └── notes_sync/
        ├── api.py           # routes (thin)
        ├── service.py       # use case, depends on ports only
        ├── ports.py         # Protocols: NoteSource, NoteConverter, VaultWriter...
        ├── domain.py        # domain objects
        ├── schemas.py       # Pydantic models (API + persistence)
        ├── config.py        # JOUSKAIO_NOTES_SYNC_*
        ├── module.py        # composition root: wires adapters into the service
        └── adapters/        # inbox, converters, pdf_text, handwriting, vault, state
```

Dependency rule: `api → service → ports ← adapters`. Services know neither the file system nor
external tools, so they are tested with fake adapters.

### Adding a module

1. Create `modules/<name>/` with `ports.py`, `service.py`, `api.py`, `adapters/`, `module.py`.
2. Expose `build_module(context: ModuleContext) -> Module` (`name`, `description`, `router()`,
   `healthcheck()`).
3. Register it in `modules/__init__.py` and enable it with
   `JOUSKAIO_ENABLED_MODULES=notes_sync,<name>`. Its routes appear under
   `/api/v1/<name-in-kebab-case>` and in their own Swagger section.
4. Document every route: `summary`, a docstring, and `responses=error_responses(...)` for each
   error it can return. `tests/integration/test_openapi.py` fails otherwise.

Module settings live in the module's `config.py` (prefix `JOUSKAIO_<NAME>_`), so disabled
modules require no variables.

Design choices: services are synchronous (file and subprocess work) and FastAPI runs them in a
thread (`BackgroundTasks`). Jobs are kept in memory: their history is lost on restart, which is
acceptable here.

## Git workflow and CI/CD

Lightweight git flow for a solo project:

- `main`: always deployable, protected (pull request and green CI required).
- `develop`: integration.
- `feature/*`, `fix/*`: short-lived branches from `develop`, merged through pull requests.
- Release: pull request `develop → main`, then a SemVer tag `vX.Y.Z` on `main`.
- **Conventional Commits** (`feat:`, `fix:`, `chore:`...), enforced by the `commitizen` hook.

```bash
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
```

- **`ci.yml`** (pull requests and pushes to `main`/`develop`): ruff, `ruff format --check`,
  strict mypy, pytest (coverage ≥ 85 %), an `ocr` job testing the real Kraken engine with its
  model, then a Docker build of both variants (with and without OCR), not pushed.
- **`release.yml`** (tags `v*.*.*`): builds and pushes two images to GHCR, `X.Y.Z`/`latest` and
  `X.Y.Z-ocr`/`latest-ocr`.
- **Deployment**: a commented job in `release.yml`, meant for a **self-hosted runner inside the
  homelab** (nothing exposed). Enable it once the runner is registered.

Protect `main` in *Settings > Branches* and require the `quality` and `ocr` jobs.

## Roadmap

- `orchestrator` module: Proxmox, Docker, Synology, media.
- Automatic triggering of `notes_sync` (periodic scan or file events) instead of a manual `POST`.
- OCR: fine-tune McCATMuS on a few pages of my own handwriting if accuracy is not enough, or plug
  a heavier engine running on another machine through the same port.
- `release-please` to generate the changelog and versions from commits.

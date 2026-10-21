# AGENTS.md

Local, 100% offline SQLite viewer/editor. FastAPI backend + vanilla JS frontend
(Fomantic-UI/Semantic UI). No frontend build step, no Node/npm — the frontend
assets are vendored and committed.

## Commands

- Sync deps: `uv sync`
- Run app: `uv run python run.py` → http://127.0.0.1:8000
- Tests: `uv run pytest`
- `run.py` env overrides: `HOST`, `PORT`, `RELOAD=true`, `ALLOWED_HOSTS`
  (comma-separated extra hostnames accepted by the request guard, e.g. a LAN
  name when binding `HOST=0.0.0.0`)
- `uv` is not always on `PATH` (and is not installed globally here). The repo's
  `.venv/` is already provisioned — fall back to it: `.venv/bin/python -m pytest`
  or `.venv/bin/python run.py`.

## Layout

- `backend/app/main.py` — builds `app`, registers all `/api/*` routers, then
  mounts `frontend/` at `/` via `StaticFiles(html=True)`. The static mount is
  added last on purpose; keep it after the API routers so `/api/*` isn't shadowed.
- `backend/app/core/` — `interfaces.py` (`BaseDataSource` ABC), `models.py`
  (Pydantic request/response models), `manager.py` (global `db_manager` singleton),
  `views_store.py` (local JSON persistence for custom views).
- `backend/app/adapters/sqlite.py` — SQLite `BaseDataSource` implementation.
- `backend/app/adapters/postgres.py` — PostgreSQL implementation (`psycopg` 3, public schema).
- `backend/app/adapters/mongo.py` — MongoDB implementation (`pymongo`, JSON command console,
  sampled schema inference).
- `backend/app/api/` — routers: `connection.py` (`/api/connection/*`,
  `/api/fs/browse`), `tables.py` (DDL), `records.py` (DML at
  `/api/tables/{name}/records`), `query.py` (`/api/query`), `views.py` (`/api/views`).
- `frontend/` — static SPA (`index.html`, `js/app.js`, vendored JS/CSS/fonts).
  The SQL console is a CodeMirror 5 editor (vendored `js/codemirror*.js` +
  `css/codemirror*.css`, Dracula dark theme) styled as a dark terminal in
  `css/custom.css`; `js/app.js` initializes it and falls back to the plain
  `<textarea>` if CodeMirror is unavailable.
- `openspec/` — spec-driven change docs; active change lives in
  `openspec/changes/create-vg-data-visor`.

## Architecture notes

- Security (`core/security.py`): there is no auth, so `LocalRequestGuard`
  rejects requests whose `Host` is not local (DNS rebinding) and browser
  requests from another origin (CSRF). There is deliberately no CORS. Tests
  pass because `tests/conftest.py` sets `ALLOWED_HOSTS=testserver`.
- Frontend: every DB- or filesystem-derived string interpolated into HTML must
  go through `escapeHtml` (table/column names and file names are attacker
  controlled when opening a foreign `.db`). `showToast` escapes for you.
- Custom views are read-only: PostgreSQL runs them in a `READ ONLY`
  transaction with bound parameters (single statement; literal `%` → `%%`),
  MongoDB rejects `$out`/`$merge` stages anywhere in the pipeline.

- To add a data source, implement `BaseDataSource`. There is no registry: routers
  call `db_manager.get_active_source()`, and only one connection is active at a
  time (local single-user app). Recent paths are in-memory only, capped at 10.
- Custom views (`views_store.py`): User-defined views based on SQL queries are
  persisted locally in `views.json` without modifying the SQLite database file.
  Queries are executed, paginated, and searched dynamically via subqueries
  (`get_query_records`). For MongoDB they store a JSON `find`/`aggregate` command
  instead of SQL; write operations are rejected.
- SQLite quirks (`sqlite.py`): `connect()` opens existing files with the
  `file:...?mode=rw` URI and raises if the file is missing or not a valid DB;
  `create_database()` raises if the file already exists. Identifiers are escaped
  with `_quote_ident` (double-quote wrapping). Tables without a primary key are
  exposed with a synthetic `rowid AS "_rowid_"`, and their DML must match on
  `rowid = ?` instead of a PK.
- MongoDB quirks (`mongo.py`): MongoDB is schemaless, so `get_schema()` samples
  documents and infers fields/types; `_id` is always the primary key. The query
  console and custom views accept JSON commands (`{"collection": "...",
  "operation": "find", ...}`), not SQL. `ConnectionInfo.path` never includes the
  password, so password-protected databases must be re-entered from the form.

## Testing

- Pytest config is duplicated in `pytest.ini` and `pyproject.toml`
  (`testpaths = tests`, `pythonpath = .`); `pytest.ini` wins.
- Tests import `backend.app.main.app` and use FastAPI's `TestClient`. They share
  the global `db_manager` singleton and open/close that single connection, so run
  them serially (no xdist/`-n`) and have each test create then close its own DB.

## Constraints

- Target Python 3.9 (`requires-python = ">=3.9"`): avoid 3.10+ syntax
  (`X | Y` unions, `match`); use `typing.Optional` / `typing.List`.
- No Node/npm. To refresh the vendored Fomantic-UI/jQuery/CodeMirror assets, run
  `python download_assets.py` (stdlib `urllib`, skips files that already exist).

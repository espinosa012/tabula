# AGENTS.md

Local, 100% offline SQLite viewer/editor. FastAPI backend + vanilla JS frontend
(Fomantic-UI/Semantic UI). No frontend build step, no Node/npm — the frontend
assets are vendored and committed.

## Commands

- Sync deps: `uv sync`
- Run app: `uv run python run.py` → http://127.0.0.1:8000
- Tests: `uv run pytest`
- `run.py` env overrides: `HOST`, `PORT`, `RELOAD=true`
- `uv` is not always on `PATH` (and is not installed globally here). The repo's
  `.venv/` is already provisioned — fall back to it: `.venv/bin/python -m pytest`
  or `.venv/bin/python run.py`.

## Layout

- `backend/app/main.py` — builds `app`, registers all `/api/*` routers, then
  mounts `frontend/` at `/` via `StaticFiles(html=True)`. The static mount is
  added last on purpose; keep it after the API routers so `/api/*` isn't shadowed.
- `backend/app/core/` — `interfaces.py` (`BaseDataSource` ABC), `models.py`
  (Pydantic request/response models), `manager.py` (global `db_manager` singleton).
- `backend/app/adapters/sqlite.py` — the only `BaseDataSource` implementation.
- `backend/app/api/` — routers: `connection.py` (`/api/connection/*`,
  `/api/fs/browse`), `tables.py` (DDL), `records.py` (DML at
  `/api/tables/{name}/records`), `query.py` (`/api/query`).
- `frontend/` — static SPA (`index.html`, `js/app.js`, vendored JS/CSS/fonts).
  The SQL console is a CodeMirror 5 editor (vendored `js/codemirror*.js` +
  `css/codemirror*.css`, Dracula dark theme) styled as a dark terminal in
  `css/custom.css`; `js/app.js` initializes it and falls back to the plain
  `<textarea>` if CodeMirror is unavailable.
- `openspec/` — spec-driven change docs; active change lives in
  `openspec/changes/create-vg-data-visor`.

## Architecture notes

- To add a data source, implement `BaseDataSource`. There is no registry: routers
  call `db_manager.get_active_source()`, and only one connection is active at a
  time (local single-user app). Recent paths are in-memory only, capped at 10.
- SQLite quirks (`sqlite.py`): `connect()` opens existing files with the
  `file:...?mode=rw` URI and raises if the file is missing or not a valid DB;
  `create_database()` raises if the file already exists. Identifiers are escaped
  with `_quote_ident` (double-quote wrapping). Tables without a primary key are
  exposed with a synthetic `rowid AS "_rowid_"`, and their DML must match on
  `rowid = ?` instead of a PK.

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

# Proposal: vg-data-visor (Local SQLite Viewer & Editor)

## Why

There is currently no visual, self-contained, and lightweight tool in this repository for inspecting and manipulating SQLite databases locally without depending on heavy desktop tools or cloud services with internet access. `vg-data-visor` solves this need by providing a local, 100% offline web application to open, create, view, edit data, and manage the schema of SQLite databases with a clear and modern interface (Semantic UI / Fomantic-UI).

## What Changes

- **Local Server and API (FastAPI)**: Creation of the Python backend that serves the REST API and the static files locally.
- **File Exploration and Connection**: Ability to open existing databases by entering a path or through a local file browser assisted by the server, and to create new SQLite databases from scratch.
- **Data Viewer and Editor (DML)**: Tabular interface with pagination, search, sorting, and editing/inserting/deleting records.
- **Schema Management (DDL)**: Visual assistant to create tables, add columns, drop tables, and an integrated SQL console for queries and free-form commands.
- **Self-Contained Web Interface (Semantic UI / Fomantic-UI)**: Static frontend with no prior build (zero-build, no Node.js/npm) with all CSS, JS, fonts, and icons packaged locally.
- **Data Abstraction Layer (`BaseDataSource`)**: Extensible, decoupled structure to support sources such as CSV, JSON, and XML in the future.

## Capabilities

### New Capabilities
- `database-connection`: Connection to local SQLite databases (by path or filesystem browser), creation of new empty SQLite databases, and recent connection history.
- `data-viewer-editor`: Tabular visualization of records per table or view (pagination, search, sorting) and CRUD operations on records (creating, editing, and deleting rows/cells).
- `schema-manager`: Visual DDL operations on SQLite (create tables with types and constraints, modify column structure, drop tables) and an interactive SQL console for executing arbitrary statements.

### Modified Capabilities
<!-- There are no previous capabilities in the project -->

## Impact

- **New code**: Full folder structure `backend/` (FastAPI, adapters, core, API) and `frontend/` (HTML and Fomantic-UI static assets).
- **Dependencies**: Lightweight Python dependencies are added (`fastapi`, `uvicorn`, `pydantic`). The backend uses `sqlite3` from the Python standard library.
- **Environment**: 100% local and offline execution, with no external connections or frontend build steps.

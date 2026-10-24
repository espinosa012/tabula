# Tasks: vg-data-visor Implementation

## 1. Project Setup and Data Layer (Backend Core)

- [x] 1.1 Set up `pyproject.toml` with `uv` (`fastapi`, `uvicorn`, `pydantic`), the folder structure (`backend/app`, `frontend/`), and the entry script `run.py`, verifying that the server starts.
- [x] 1.2 Define the abstract interface `BaseDataSource` and the Pydantic models (`backend/app/core/`), verifying imports and type validation.
- [x] 1.3 Implement the `SQLiteDataSource` adapter for file connections, creating a new DB, and introspecting tables and schemas, verifying with unit tests on SQLite.
- [x] 1.4 Implement DML methods in `SQLiteDataSource` (paginated reads, filters, sorting, insertion, updates by PK/rowid, and deletion), verifying with data operation tests.
- [x] 1.5 Implement DDL methods and query execution in `SQLiteDataSource` (creating tables, altering columns, DROP TABLE, and the SQL console), verifying correct execution of DDL statements.

## 2. REST API Endpoints

- [x] 2.1 Implement the connections router and local filesystem browser (`/api/connection/open`, `/api/connection/create`, `/api/connection/recent`, `/api/fs/browse`), verifying with navigation and connection tests.
- [x] 2.2 Implement the schema and tables router (`/api/tables`, `/api/tables/{name}/schema`, `/api/tables/create`, `/api/tables/{name}/alter`, `/api/tables/{name}/drop`), verifying JSON responses and status codes.
- [x] 2.3 Implement the data and records router (`/api/tables/{name}/records` GET, POST, PUT, DELETE) with pagination, filters, and sorting, verifying that changes persist in SQLite.
- [x] 2.4 Implement the query execution router (`/api/query`), verifying the tabular response for SELECT and the reporting of affected rows or errors in DDL/DML.

## 3. Static Frontend with Fomantic-UI (100% Offline)

- [x] 3.1 Download and integrate the Fomantic-UI distribution files (CSS and JS), jQuery, fonts, and FontAwesome/Semantic icons locally into `frontend/` for offline operation.
- [x] 3.2 Develop the initial connection view in `frontend/index.html` (open an existing file by path, server folder browser modal, create an empty database, and recent history).
- [x] 3.3 Develop the data viewer and editor (sidebar with tables and views, grid with configurable pagination, search/filter, sorting by column, record editor modal/inline, and delete confirmation).
- [x] 3.4 Develop the DDL schema designer (table creation modal with typed columns and constraints, add column modal, and a confirmation dialog for DROP TABLE).
- [x] 3.5 Develop the interactive SQL Console tab (textarea for free-form statements, run button, and results table with time and error reporting).

## 4. System Integration and Verification

- [x] 4.1 Configure the static file service in FastAPI by mounting `frontend/` at the root (`/`) to serve the application as a SPA without requiring an external web server.
- [x] 4.2 Run an integral end-to-end test: create a new database from scratch, define a table with DDL, insert and edit records, and run complex queries in the SQL console.

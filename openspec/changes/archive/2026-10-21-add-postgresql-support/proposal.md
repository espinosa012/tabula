# Proposal

## Why

vg-data-visor currently only supports local SQLite database files. Users need to connect to PostgreSQL databases—both local instances (such as local Docker or Postgres services) and remote cloud databases (such as Neon, Supabase, AWS RDS)—and perform the same catalog inspection, table DDL, paginated record viewing/editing, SQL console queries, and custom views seamlessly through the existing interface.

## What Changes

- **PostgreSQL Adapter**: Introduce `PostgreSQLDataSource` implementing `BaseDataSource` using `psycopg` (v3 binary) with automatic type serialization (UUID, datetime/timestamps, Decimal, JSON/JSONB).
- **Flexible Connection Methods**: Support connecting to PostgreSQL via individual fields (Host, Port, Database, Username, Password, SSL Mode) as well as direct Connection URLs (`postgresql://user:password@host:port/dbname?sslmode=...`).
- **Connection Testing**: Add an endpoint (`POST /api/connection/postgres/test`) to validate connection credentials without altering the active session.
- **Active Connection Management**: Add `POST /api/connection/postgres/connect` to activate the PostgreSQL data source in `db_manager`.
- **Public Schema Support**: Inspect and query tables, views, columns, and constraints specifically for the `public` schema (`SET search_path TO public;`).
- **Tables Without Primary Keys**: Support updating and deleting records in tables lacking a PK by projecting `ctid::text` as `_rowid_` and executing targeted DML via `WHERE ctid = %s::tid`.
- **Dynamic Connection UI**: Enhance the initial connection view with an engine selector (SQLite vs PostgreSQL) and dynamic sub-forms (Form fields vs Connection URL) with connection testing feedback.
- **Top Bar & Views Compatibility**: Display PostgreSQL connection info (`db_name @ host`) in the navbar, and allow saving and filtering Custom Views for PostgreSQL databases.

## Capabilities

### New Capabilities
- `postgresql-datasource`: Connect to, inspect schemas, query, and edit records in local and remote PostgreSQL databases on the `public` schema with full parity to the SQLite workflow.

### Modified Capabilities
<!-- None -->

## Impact

- **Dependencies**: Add `psycopg[binary]>=3.1.0` to `pyproject.toml`.
- **Core Models**: New connection request models in `backend/app/core/models.py`.
- **Adapters**: New file `backend/app/adapters/postgres.py`.
- **API**: New routes in `backend/app/api/connection.py`.
- **Views**: Update `backend/app/core/views_store.py` so PostgreSQL identifiers are preserved without filesystem path resolution.
- **Frontend**: Update `frontend/index.html` and `frontend/js/app.js` with the dynamic connection UI and status indicators.
- **Tests**: Add unit and integration tests for PostgreSQL adapter and connection endpoints.

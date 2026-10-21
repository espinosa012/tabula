# Design

## Context

vg-data-visor is built around a single-active-source architecture:
- `BaseDataSource` (`backend/app/core/interfaces.py`) defines the contract for catalog inspection, DDL, DML, and query execution.
- `DataSourceManager` (`backend/app/core/manager.py`) holds the currently connected instance.
- The FastAPI routers (`tables.py`, `records.py`, `query.py`, `views.py`) invoke the active source without depending on SQLite-specific APIs.
- The project targets Python >= 3.9 and runs synchronously in FastAPI worker threads.

See `proposal.md` for background and motivation.

## Goals / Non-Goals

**Goals:**
- Implement `PostgreSQLDataSource` fulfilling `BaseDataSource` using `psycopg` 3 (`psycopg[binary]`).
- Support local (e.g. Docker, standard port 5432) and remote cloud instances (e.g. Neon, Supabase, RDS) with configurable SSL modes.
- Support both individual connection parameters (host, port, db, user, password, sslmode) and direct Connection URIs.
- Provide a non-destructive connection testing endpoint (`/api/connection/postgres/test`).
- Expose `ctid::text` as `_rowid_` for tables lacking primary keys, ensuring 100% frontend edit/delete parity with SQLite.
- Build a responsive, dynamic connection UI in the frontend allowing seamless switching between SQLite and PostgreSQL modes.

**Non-Goals:**
- Multiple schema exploration: fixed to the `public` schema (`SET search_path TO public;`).
- Multi-database concurrent connections: the application continues to operate on a single active connection at a time.
- Database administration: creating new databases or managing user roles/permissions on PostgreSQL servers is out of scope.

## Decisions

### 1. Driver Selection: `psycopg` (v3) over `psycopg2` or `asyncpg`
- **Choice**: `psycopg[binary]>=3.1.0`.
- **Rationale**: Modern, actively maintained, has wheels with embedded `libpq` (no host compiler or OS packages needed), fully supports Python 3.9+, and provides native type adaptation.
- **Alternatives considered**:
  - `psycopg2-binary`: Older generation, less clean typing, being superseded by psycopg 3.
  - `asyncpg`: Excellent performance, but the current backend uses synchronous FastAPI endpoint functions (`def`), which would require rewriting all routers to `async def`.

### 2. Transaction Handling: Autocommit Mode
- **Choice**: Open connections with `autocommit=True` on `psycopg.connect`.
- **Rationale**: In PostgreSQL, when an error occurs in a transaction, the entire block is aborted until `ROLLBACK`. Autocommit prevents a failed ad-hoc query from locking subsequent queries in the console or data grid. Explicit DDL and DML operations execute independently.

### 3. Row Identification: `ctid::text AS "_rowid_"` for Tables Without PK
- **Choice**: Project `ctid::text` aliased as `_rowid_` when `pk_columns` is empty.
- **Rationale**: The existing frontend (`app.js`) already checks for `_rowid_` when selecting rows for update or delete modals. By aliasing `ctid` as `_rowid_` and generating `WHERE ctid = %s::tid` on the backend, zero changes are required in the frontend record editor.
- **Alternatives considered**:
  - Requiring primary keys: Restrictive for legacy or read-heavy tables.
  - Matching all column values: Prone to errors with NULL values or floating-point imprecision.

### 4. Robust Value Serialization
- **Choice**: Centralized `_serialize_pg_value(val)` function in the adapter.
- **Rationale**: PostgreSQL produces types that Python's default `json.dumps` and Pydantic cannot serialize directly without custom encoders (`UUID`, `datetime`, `Decimal`, `bytes`). Converting them uniformly to standard strings/floats/booleans ensures FastAPI endpoints never return 500 serialization errors.

### 5. Dynamic Frontend Connection View
- **Choice**: Segmented toggle between SQLite and PostgreSQL in `index.html`. Under PostgreSQL, radio toggle between "Form Parameters" and "Connection URL".
- **Rationale**: Different cloud providers provide connection strings while local databases are easier to enter as host/port/user. Supporting both provides the best developer experience.

## Risks / Trade-offs

- **[Risk] Remote connections can drop due to idle timeouts** → **Mitigation**: Use `connect_timeout` and handle reconnections or clear error messages when connections become stale.
- **[Risk] `ctid` is not permanent across VACUUM FULL** → **Mitigation**: `ctid` is queried immediately before interactive editing in the UI session; operations are near-immediate and safe for interactive data viewing.
- **[Risk] Views store path resolution** → **Mitigation**: Update `views_store.py` so database identifiers with URL schemes (e.g. `postgres://...`) bypass `os.path.abspath`.

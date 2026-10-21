# Tasks

## 1. Dependencies and Core Models

- [x] 1.1 Add `psycopg[binary]>=3.1.0` to `pyproject.toml` and sync the project dependencies, verifying `import psycopg` succeeds in Python 3.9
- [x] 1.2 Define PostgreSQL connection models (`PostgresConnectionParams`, `PostgresConnectionUri`, `PostgresConnectRequest`, and updated `ConnectionInfo`) in `backend/app/core/models.py` and verify model validation with unit tests

## 2. PostgreSQL Adapter Implementation

- [x] 2.1 Implement `PostgreSQLDataSource` connection management (`connect`, `close`, `is_connected`, `get_connection_info`) supporting both URL strings and parameter dictionaries with `autocommit=True` in `backend/app/adapters/postgres.py`
- [x] 2.2 Implement `_serialize_pg_value` to convert UUIDs, datetimes, Decimals, and bytes into JSON-compatible values, verifying serialization on sample data
- [x] 2.3 Implement `list_collections` and `get_schema` in `PostgreSQLDataSource` restricted to the `public` schema (`table_schema = 'public'`)
- [x] 2.4 Implement `get_records` and `get_query_records` with pagination, sorting, case-insensitive `ILIKE` search, and `ctid::text AS "_rowid_"` projection for tables without primary keys
- [x] 2.5 Implement DML operations (`insert_record`, `update_record`, `delete_record`) supporting primary keys and `ctid = %s::tid` targeting
- [x] 2.6 Implement DDL operations (`create_table`, `add_column`, `rename_table`, `drop_table`) and `execute_query` in `PostgreSQLDataSource`

## 3. Backend API Endpoints & Views Store Compatibility

- [x] 3.1 Implement `POST /api/connection/postgres/test` (credential test without session activation) and `POST /api/connection/postgres/connect` (activate data source) in `backend/app/api/connection.py`
- [x] 3.2 Update `backend/app/core/views_store.py` so PostgreSQL database identifiers bypass filesystem path resolution (`os.path.abspath`)
- [x] 3.3 Create test suite in `tests/test_postgres_adapter.py` and `tests/test_postgres_api.py` testing connection parsing, type serialization, and API endpoints

## 4. Dynamic Frontend UI & Verification

- [x] 4.1 Update `frontend/index.html` to introduce the database engine selector (SQLite vs PostgreSQL), dynamic form fields (Form vs Connection URL), and "Test Connection" button
- [x] 4.2 Update `frontend/js/app.js` to handle dynamic form visibility, connection testing, PostgreSQL connection dispatch, recent connections, and top navbar status display
- [x] 4.3 Run full test suite (`pytest`) to verify no regressions in SQLite functionality and all new tests pass cleanly

# Design

## Context

The application is built around a single-active-source architecture:

- `BaseDataSource` (`backend/app/core/interfaces.py`) defines catalog inspection, DDL, DML, and query execution.
- `DataSourceManager` (`backend/app/core/manager.py`) holds the connected instance.
- FastAPI routers (`tables.py`, `records.py`, `query.py`, `views.py`) call the active source without SQLite-specific assumptions.
- The frontend is a vanilla-JS SPA that renders whatever columns/records the adapter returns.

MongoDB differs from SQL in three important ways: it has no fixed schema, it identifies documents by `_id`, and its query language is JSON rather than SQL. The adapter must bridge those differences without changing the router contracts.

## Goals / Non-Goals

**Goals:**

- Implement `MongoDataSource` with `pymongo` (synchronous, matching the existing `def` endpoints).
- Connect to local (`mongodb://localhost:27017`) and remote (`mongodb+srv://...`, TLS) deployments.
- Support individual parameters and connection URIs, with a non-destructive test endpoint.
- Infer a useful schema by sampling documents, always exposing `_id` as the primary key.
- Keep pagination, search, sorting, and CRUD semantics identical to the SQL adapters.
- Expose a JSON command console and JSON custom views.
- Light up MongoDB-specific labels in the SPA while sharing all existing components.

**Non-Goals:**

- Multi-database browsing inside one session (one active database at a time, as with PostgreSQL).
- Real `mongosh` JavaScript evaluation (only JSON commands are accepted).
- Replica-set administration, user management, or index management UI.
- Perfect schema fidelity for collections whose documents vary (schema is inferred from a sample).

## Decisions

### 1. Driver: `pymongo` rather than Motor or the MongoDB shell

- **Choice**: `pymongo>=4.6`.
- **Rationale**: The backend endpoints are synchronous; Motor would force an async rewrite. `pymongo` is the official driver, ships wheels for Python 3.9+, and includes `bson.json_util` for Extended JSON.
- **Alternatives**: `motor` (async), `mongoengine` (ODM, unnecessary abstraction).

### 2. Schema inference from a sample

- **Choice**: Sample up to 50 documents per collection and build a union of fields in first-seen order. Types are the union of observed BSON types (e.g. `string`, `int`, `ObjectId`). A field is `not_null` when it appears in every sampled document.
- **Rationale**: MongoDB has no catalog of columns. Sampling gives the UI meaningful labels, PK detection, and sensible coercion without scanning the whole collection.
- **Trade-off**: Documents with fields absent from the sample still appear in the data grid because `get_records` appends any extra keys found in the returned page.

### 3. `_id` as the record identifier

- **Choice**: Treat `_id` as the primary key; convert valid 24-hex strings back to `ObjectId` on update/delete.
- **Rationale**: Reuses the existing frontend PK flow (`pk_columns`) with zero special cases. `_rowid_` is not needed because every MongoDB document has `_id`.
- **Trade-off**: Collections with non-ObjectId `_id` values are supported (the string is kept as-is), but the UI does not offer `_rowid_`-style fallback for documents that somehow omit `_id` (MongoDB always adds one).

### 4. JSON command console

- **Choice**: Accept a JSON object with a `collection` and optional `operation`:
  ```json
  {"collection": "users", "operation": "find", "filter": {"active": true}, "limit": 50}
  ```
  Supported operations: `find`, `findOne`, `aggregate`, `count`, `distinct`, `insertOne`, `insertMany`, `updateOne`, `updateMany`, `replaceOne`, `deleteOne`, `deleteMany`, `listCollections`.
- **Rationale**: JSON is native to MongoDB, easy to parse, and expressible in the existing CodeMirror editor. Reusing `/api/query` avoids a second console endpoint.
- **Alternatives**: Parsing `db.users.find(...)` shell syntax (fragile), adding a JavaScript runtime (heavy and unsafe).

### 5. Custom views as saved find/aggregate commands

- **Choice**: `get_query_records` accepts a `find` or `aggregate` command. Search is translated to a case-insensitive `$regex` `$or` over inferred fields (plus an `ObjectId` match when the term is a valid id), and pagination is translated to `skip`/`limit` (or `$skip`/`$limit` for aggregations).
- **Rationale**: Preserves the existing custom-view UI and server-side pagination without pulling entire collections into memory.
- **Trade-off**: Write operations cannot be saved as custom views.

### 6. Connection display path without secrets

- **Choice**: `ConnectionInfo.path` is `mongodb://[user@]host:port/database` and never includes the password, matching the PostgreSQL adapter.
- **Rationale**: The path is shown in the navbar, recent list, and `views.json`. Recent connections that require a password must be re-entered through the connection form.

## Risks / Trade-offs

- **[Risk] Schema sample misses fields** → **Mitigation**: `get_records` augments columns with keys present in the current page.
- **[Risk] `estimated_document_count` can be approximate** → **Mitigation**: it is a display-only count; pagination uses `count_documents` with the actual filter for an exact total.
- **[Risk] Search on non-string fields** → **Mitigation**: `$regex` only matches string values; valid `ObjectId` terms are matched exactly, so `_id` searches still work.
- **[Risk] Adding a field with a default rewrites every document** → **Mitigation**: only performed on an explicit user action; a no-default add is a no-op because MongoDB is schemaless.
- **[Risk] Password not preserved in recents** → **Mitigation**: documented behavior consistent with PostgreSQL; users re-enter credentials for secured deployments.

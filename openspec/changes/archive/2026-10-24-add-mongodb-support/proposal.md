# Proposal

## Why

vg-data-visor already supports local SQLite files and local/remote PostgreSQL databases. Users also need to inspect and edit MongoDB databases—both a local `mongod` and remote deployments such as MongoDB Atlas—without leaving the same interface.

## What Changes

- **MongoDB Adapter**: Introduce `MongoDataSource` implementing `BaseDataSource` with `pymongo`, including document serialization for BSON types (`ObjectId`, dates, decimals, binary, nested objects/arrays).
- **Flexible Connection Methods**: Connect with individual fields (host, port, database, user, password, auth source, TLS) or a connection URI (`mongodb://`, `mongodb+srv://`).
- **Connection Testing**: Add `POST /api/connection/mongo/test` to validate credentials without replacing the active session, and `POST /api/connection/mongo/connect` to activate the source.
- **Collections and Schema Inference**: List collections and views, and infer fields/types by sampling documents (MongoDB is schemaless). `_id` is exposed as the primary key.
- **Document CRUD**: Paginated, searchable, sortable documents; insert, update, and delete using `_id` as the record identifier.
- **MongoDB Query Console**: Reuse the existing console with JSON commands (`find`, `aggregate`, `count`, `insertOne`, `updateOne`, `deleteOne`, etc.) accepted by `/api/query`.
- **Custom Views**: Save MongoDB `find`/`aggregate` JSON commands as custom views, with the same pagination, search, and sorting behavior.
- **Dynamic Frontend UI**: Add a third engine selector (SQLite / PostgreSQL / MongoDB) with parameter and URI forms, test feedback, recent connections, and MongoDB-aware labels/presets in the workspace.

## Capabilities

### New Capabilities
- `mongodb-datasource`: Connect to, inspect, query, and edit local and remote MongoDB databases with feature parity to the existing SQLite/PostgreSQL workflows.

### Modified Capabilities
- `postgresql-datasource`: `ConnectionInfo` gains an optional `port` field populated by network adapters (no behavioral change for PostgreSQL connections).

## Impact

- **Dependencies**: Add `pymongo>=4.6` (and `mongomock` for tests) to `pyproject.toml`.
- **Core Models**: MongoDB connection/test models plus optional `port` in `ConnectionInfo`.
- **Adapters**: New file `backend/app/adapters/mongo.py`.
- **API**: New routes in `backend/app/api/connection.py`.
- **Frontend**: Engine selector, MongoDB connection forms, recent connections, and dynamic collection/query labels in `frontend/index.html` and `frontend/js/app.js`.
- **Tests**: New unit/API tests for the MongoDB adapter, models, and connection endpoints.

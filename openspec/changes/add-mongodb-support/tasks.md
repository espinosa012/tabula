# Tasks

## 1. Dependencies and Core Models

- [x] 1.1 Add `pymongo>=4.6` (and `mongomock` for tests) to `pyproject.toml`, install them, and verify `import pymongo` on Python 3.9
- [x] 1.2 Add MongoDB connection models (`MongoConnectionParams`, `MongoConnectRequest`, `MongoTestResponse`) and an optional `port` field to `ConnectionInfo` in `backend/app/core/models.py`

## 2. MongoDB Adapter Implementation

- [x] 2.1 Implement `MongoDataSource` connection management (`connect`, `close`, `is_connected`, `get_connection_info`) for parameters and URIs, with `serverSelectionTimeoutMS` and ping validation
- [x] 2.2 Implement BSON serialization (`_serialize_mongo_value`) and value coercion (`_coerce_value`) for ObjectId, dates, decimals, binary, booleans, numbers, objects, and arrays
- [x] 2.3 Implement `list_collections` and sampled `get_schema` (union of fields, inferred types, `_id` as primary key, view detection)
- [x] 2.4 Implement `get_records` and `get_query_records` with pagination, sorting, case-insensitive search, and exact filtered totals
- [x] 2.5 Implement document CRUD (`insert_record`, `update_record`, `delete_record`) using `_id` (ObjectId-aware) and `$set`
- [x] 2.6 Implement collection DDL (`create_table`, `add_column`, `rename_table`, `drop_table`) and the JSON `execute_query` command set

## 3. Backend API

- [x] 3.1 Add `POST /api/connection/mongo/test` and `POST /api/connection/mongo/connect` in `backend/app/api/connection.py`
- [x] 3.2 Confirm custom views work with MongoDB paths and JSON commands (`views_store.py` already treats `://` identifiers as network ids)

## 4. Frontend UI

- [x] 4.1 Add the MongoDB engine button, parameter/URI connection forms, test feedback, and recent-connections list to `frontend/index.html`
- [x] 4.2 Update `frontend/js/app.js` for MongoDB connection dispatch, status display, recent-connection classification, and engine switching
- [x] 4.3 Make the workspace labels, record modal, console title/prompt/presets, and custom-view modal MongoDB-aware

## 5. Tests and Verification

- [x] 5.1 Add `tests/test_mongo_models.py`, `tests/test_mongo_adapter.py`, and `tests/test_mongo_api.py`
- [x] 5.2 Run the full pytest suite serially and verify no SQLite/PostgreSQL regressions

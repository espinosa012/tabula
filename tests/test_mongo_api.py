"""Integration tests for the MongoDB connection and workspace endpoints."""
import mongomock
import pytest
from fastapi.testclient import TestClient

import backend.app.adapters.mongo as mongo_module
from backend.app.core.manager import db_manager
from backend.app.main import app

client = TestClient(app)


@pytest.fixture
def mongo_client(monkeypatch):
    """Route every MongoClient created by the adapter to an in-memory server."""
    fake_server = mongomock.MongoClient()
    monkeypatch.setattr(mongo_module, "MongoClient", lambda *args, **kwargs: fake_server)
    client.post("/api/connection/close")
    yield fake_server
    client.post("/api/connection/close")


def test_api_mongo_test_connection(mongo_client):
    params_payload = {
        "mode": "params",
        "params": {
            "host": "localhost",
            "port": 27017,
            "database": "testdb",
            "user": "",
            "password": "",
            "auth_source": "admin",
            "tls": False,
        },
    }
    res = client.post("/api/connection/mongo/test", json=params_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["database"] == "testdb"

    uri_res = client.post(
        "/api/connection/mongo/test",
        json={"mode": "uri", "uri": "mongodb://localhost:27017/otherdb"},
    )
    assert uri_res.status_code == 200
    assert uri_res.json()["database"] == "otherdb"

    missing_res = client.post("/api/connection/mongo/test", json={"mode": "params"})
    assert missing_res.status_code == 400


def test_api_mongo_connect_and_crud_workflow(mongo_client):
    res = client.post(
        "/api/connection/mongo/connect",
        json={
            "mode": "params",
            "params": {
                "host": "localhost",
                "port": 27017,
                "database": "testdb",
                "user": "",
                "password": "",
                "auth_source": "admin",
                "tls": False,
            },
        },
    )
    assert res.status_code == 200
    info = res.json()
    assert info["connected"] is True
    assert info["db_type"] == "mongo"
    assert info["database"] == "testdb"
    assert info["port"] == 27017

    # The connection is active.
    assert client.get("/api/connection/status").json()["connected"] is True
    assert db_manager.is_connected() is True

    # Create a collection.
    res_create = client.post(
        "/api/tables/create",
        json={"name": "users", "columns": [{"name": "name", "type": "string"}]},
    )
    assert res_create.status_code == 200

    # Insert documents (the schema is schemaless, so any field is accepted).
    res_ins = client.post(
        "/api/tables/users/records",
        json={"values": {"name": "Alice", "age": "30", "active": "true"}},
    )
    assert res_ins.status_code == 200
    alice = res_ins.json()
    assert alice["name"] == "Alice"
    assert alice["age"] == 30

    client.post("/api/tables/users/records", json={"values": {"name": "Bob", "age": "25"}})

    # Tables/collections listing and inferred schema.
    tables = client.get("/api/tables").json()
    assert [table["name"] for table in tables] == ["users"]
    schema = client.get("/api/tables/users/schema").json()
    assert schema["pk_columns"] == ["_id"]
    assert schema["columns"][0]["name"] == "_id"
    assert {column["name"] for column in schema["columns"]} >= {"_id", "name", "age"}

    # Paginated records and search.
    page = client.get("/api/tables/users/records?page=1&page_size=1").json()
    assert page["total"] == 2
    assert page["total_pages"] == 2
    search = client.get("/api/tables/users/records?search=alice").json()
    assert search["total"] == 1
    assert search["records"][0]["name"] == "Alice"

    # Update and delete by ObjectId.
    res_upd = client.put(
        "/api/tables/users/records",
        json={"pk_values": {"_id": alice["_id"]}, "values": {"age": "31"}},
    )
    assert res_upd.status_code == 200
    assert res_upd.json()["age"] == 31

    # JSON query console.
    res_query = client.post(
        "/api/query",
        json={
            "query": '{"collection": "users", "operation": "find", "filter": {"name": "Alice"}}'
        },
    )
    assert res_query.status_code == 200
    assert res_query.json()["rows"][0]["age"] == 31

    # Custom view from a find command.
    res_view = client.post(
        "/api/views",
        json={
            "name": "Active users",
            "sql": '{"collection": "users", "filter": {"age": {"$gte": 25}}}',
        },
    )
    assert res_view.status_code == 201
    view_id = res_view.json()["id"]
    view_records = client.get(f"/api/views/{view_id}/records").json()
    assert view_records["total"] == 2

    # Write commands cannot be saved as views.
    bad_view = client.post(
        "/api/views",
        json={
            "name": "Bad",
            "sql": '{"collection": "users", "operation": "insertOne", "document": {}}',
        },
    )
    assert bad_view.status_code == 400

    res_del = client.post(
        "/api/tables/users/records/delete", json={"pk_values": {"_id": alice["_id"]}}
    )
    assert res_del.status_code == 200
    assert client.get("/api/tables/users/records").json()["total"] == 1

    # Clean up the created view.
    client.delete(f"/api/views/{view_id}")

    # Drop the collection and disconnect.
    assert client.delete("/api/tables/users/drop").status_code == 200
    assert client.post("/api/connection/close").status_code == 200
    assert client.get("/api/connection/status").json()["connected"] is False


def test_api_mongo_connect_failure_keeps_session_intact(mongo_client, monkeypatch):
    # First open a SQLite-free session using mongomock.
    client.post(
        "/api/connection/mongo/connect",
        json={
            "mode": "uri",
            "uri": "mongodb://localhost:27017/testdb",
        },
    )
    assert db_manager.is_connected() is True

    def fail_client(*args, **kwargs):
        raise RuntimeError("server selection timed out")

    monkeypatch.setattr(mongo_module, "MongoClient", fail_client)
    res = client.post(
        "/api/connection/mongo/connect",
        json={"mode": "uri", "uri": "mongodb://bad-host:27017/testdb"},
    )
    assert res.status_code == 400
    assert "Failed to connect to MongoDB" in res.json()["detail"]
    # The previous source is still active.
    assert client.get("/api/connection/status").json()["connected"] is True

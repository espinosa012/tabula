"""Tests verifying refresh and synchronization behaviors across API endpoints."""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


@pytest.fixture
def refresh_db():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    if os.path.exists(path):
        os.remove(path)

    # Create and connect DB
    res = client.post("/api/connection/create", json={"path": path})
    assert res.status_code == 200

    yield path

    client.post("/api/connection/close")
    if os.path.exists(path):
        os.remove(path)


def test_refresh_connection_status_and_size(refresh_db):
    """Ensure connection status updates dynamically and reflects size changes."""
    status_initial = client.get("/api/connection/status").json()
    assert status_initial["connected"] is True
    initial_size = status_initial["size_bytes"]

    # Create table with several rows
    client.post(
        "/api/tables/create",
        json={
            "name": "logs",
            "columns": [
                {"name": "id", "type": "INTEGER", "is_pk": True, "auto_increment": True},
                {"name": "message", "type": "TEXT"},
            ],
        },
    )

    for i in range(100):
        client.post("/api/tables/logs/records", json={"values": {"message": f"Log entry {i} with padding text " * 10}})

    # Check connection status again
    status_after = client.get("/api/connection/status").json()
    assert status_after["connected"] is True
    assert status_after["tables_count"] == 1
    assert status_after["size_bytes"] >= initial_size


def test_refresh_table_row_counts(refresh_db):
    """Ensure /api/tables row_count reflects record additions and deletions."""
    client.post(
        "/api/tables/create",
        json={
            "name": "items",
            "columns": [
                {"name": "id", "type": "INTEGER", "is_pk": True, "auto_increment": True},
                {"name": "name", "type": "TEXT"},
            ],
        },
    )

    # Initial table list
    tables = client.get("/api/tables").json()
    assert len(tables) == 1
    assert tables[0]["row_count"] == 0

    # Insert 3 records
    for name in ["A", "B", "C"]:
        client.post("/api/tables/items/records", json={"values": {"name": name}})

    # Refresh tables list
    tables_after = client.get("/api/tables").json()
    assert tables_after[0]["row_count"] == 3

    # Delete 1 record
    client.post("/api/tables/items/records/delete", json={"pk_values": {"id": 1}})

    # Refresh tables list again
    tables_deleted = client.get("/api/tables").json()
    assert tables_deleted[0]["row_count"] == 2


def test_refresh_schema_after_alter(refresh_db):
    """Ensure table schema updates immediately when altered via SQL or API."""
    client.post(
        "/api/tables/create",
        json={
            "name": "users",
            "columns": [{"name": "id", "type": "INTEGER", "is_pk": True}],
        },
    )

    schema_before = client.get("/api/tables/users/schema").json()
    assert len(schema_before["columns"]) == 1

    # Alter table via SQL query
    client.post("/api/query", json={"query": "ALTER TABLE users ADD COLUMN email TEXT;"})

    schema_after = client.get("/api/tables/users/schema").json()
    col_names = [c["name"] for c in schema_after["columns"]]
    assert "email" in col_names


def test_refresh_view_records_when_underlying_table_changes(refresh_db):
    """Ensure custom views return fresh data when source tables are modified."""
    client.post(
        "/api/tables/create",
        json={
            "name": "scores",
            "columns": [
                {"name": "id", "type": "INTEGER", "is_pk": True, "auto_increment": True},
                {"name": "player", "type": "TEXT"},
                {"name": "score", "type": "INTEGER"},
            ],
        },
    )

    client.post("/api/tables/scores/records", json={"values": {"player": "Alice", "score": 100}})

    # Create view
    res_view = client.post(
        "/api/views",
        json={"name": "high_scores", "sql": 'SELECT player, score FROM scores WHERE score >= 50'},
    )
    assert res_view.status_code == 201
    view_id = res_view.json()["id"]

    # Read view records
    view_records1 = client.get(f"/api/views/{view_id}/records").json()
    assert view_records1["total"] == 1

    # Add another record to scores
    client.post("/api/tables/scores/records", json={"values": {"player": "Bob", "score": 80}})

    # Read view records again (refresh)
    view_records2 = client.get(f"/api/views/{view_id}/records").json()
    assert view_records2["total"] == 2

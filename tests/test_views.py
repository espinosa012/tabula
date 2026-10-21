"""Tests for custom views: storage, adapter querying, and REST endpoints."""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from backend.app.adapters.sqlite import SQLiteDataSource
from backend.app.core.manager import db_manager
from backend.app.core.models import (
    ColumnDefinition,
    CreateTableRequest,
    PaginationParams,
)
from backend.app.core.views_store import ViewsStore, views_store
from backend.app.main import app

client = TestClient(app)


@pytest.fixture
def temp_db_path():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def temp_views_file():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_views_store_crud(temp_views_file):
    store = ViewsStore(file_path=temp_views_file)
    assert store.list_views() == []

    # Create view
    v1 = store.create_view(
        name="Active Users",
        sql="SELECT * FROM users WHERE active = 1",
        description="Only active users",
        db_path="/tmp/test.db",
    )
    assert v1.id.startswith("view_")
    assert v1.name == "Active Users"
    assert v1.sql == "SELECT * FROM users WHERE active = 1"
    assert v1.description == "Only active users"
    assert v1.db_path == os.path.abspath("/tmp/test.db")

    # Read back from disk with new store instance
    store2 = ViewsStore(file_path=temp_views_file)
    views = store2.list_views()
    assert len(views) == 1
    assert views[0].id == v1.id
    assert views[0].name == "Active Users"

    # Get single
    found = store2.get_view(v1.id)
    assert found is not None
    assert found.name == "Active Users"

    # Filter by db_path
    assert len(store2.list_views(db_path="/tmp/test.db")) == 1
    assert len(store2.list_views(db_path="/tmp/other.db")) == 0

    # Global view (no db_path) appears for any db
    v_global = store.create_view(
        name="Global Info",
        sql="SELECT 1 as num",
        db_path=None,
    )
    matched = store.list_views(db_path="/tmp/other.db")
    assert len(matched) == 1
    assert matched[0].id == v_global.id

    # Update view
    updated = store.update_view(v1.id, name="All Active Users", sql="SELECT id, name FROM users WHERE active = 1")
    assert updated is not None
    assert updated.name == "All Active Users"
    assert updated.sql == "SELECT id, name FROM users WHERE active = 1"
    assert updated.description == "Only active users"  # preserved

    # Delete view
    assert store.delete_view(v1.id) is True
    assert store.get_view(v1.id) is None
    assert store.delete_view("nonexistent") is False


def test_sqlite_adapter_get_query_records(temp_db_path):
    ds = SQLiteDataSource()
    ds.create_database(temp_db_path)

    # Setup tables and data
    ds.create_table(
        CreateTableRequest(
            name="products",
            columns=[
                ColumnDefinition(name="id", type="INTEGER", is_pk=True, auto_increment=True),
                ColumnDefinition(name="name", type="TEXT"),
                ColumnDefinition(name="category", type="TEXT"),
                ColumnDefinition(name="price", type="REAL"),
            ],
        )
    )
    for i in range(1, 26):
        cat = "Electronics" if i % 2 == 0 else "Books"
        ds.insert_record("products", {"name": f"Item {i}", "category": cat, "price": i * 10.0})

    # Test basic paginated query
    query = "SELECT id, name, category, price FROM products WHERE price > 50"
    records = ds.get_query_records(query, PaginationParams(page=1, page_size=10, sort_by="price", sort_dir="asc"))
    assert records.total == 20
    assert len(records.records) == 10
    assert records.columns == ["id", "name", "category", "price"]
    assert records.records[0]["price"] == 60.0
    assert records.records[9]["price"] == 150.0

    # Test search filter within query
    search_res = ds.get_query_records(query, PaginationParams(page=1, page_size=10, search="Books"))
    assert search_res.total == 10
    assert all(r["category"] == "Books" for r in search_res.records)

    # Test query with trailing semicolons and whitespace
    dirty_query = f"   {query};;;   "
    clean_res = ds.get_query_records(dirty_query, PaginationParams(page=1, page_size=5))
    assert clean_res.total == 20
    assert len(clean_res.records) == 5

    # Test CTE query
    cte_query = "WITH high_price AS (SELECT * FROM products WHERE price >= 200) SELECT name, price FROM high_price"
    cte_res = ds.get_query_records(cte_query, PaginationParams(page=1, page_size=10))
    assert cte_res.total == 6

    # Test duplicate column names in query
    dup_query = "SELECT id, name, name FROM products LIMIT 5"
    dup_res = ds.get_query_records(dup_query, PaginationParams(page=1, page_size=5))
    assert len(dup_res.columns) == 3
    assert len(set(dup_res.columns)) == 3
    assert "name" in dup_res.columns
    assert len(dup_res.records) == 5

    # Test invalid query raises ValueError
    with pytest.raises(ValueError):
        ds.get_query_records("SELECT FROM INVALID SYNTAX", PaginationParams(page=1, page_size=5))

    ds.close()


def test_custom_views_api(temp_db_path, temp_views_file, monkeypatch):
    # Point global store to temporary file
    test_store = ViewsStore(file_path=temp_views_file)
    monkeypatch.setattr("backend.app.api.views.views_store", test_store)

    # Create and connect DB
    res_open = client.post("/api/connection/create", json={"path": temp_db_path})
    assert res_open.status_code == 200

    # Create table 'orders'
    client.post(
        "/api/tables/create",
        json={
            "name": "orders",
            "columns": [
                {"name": "id", "type": "INTEGER", "is_pk": True},
                {"name": "customer", "type": "TEXT"},
                {"name": "status", "type": "TEXT"},
                {"name": "total", "type": "REAL"},
            ],
        },
    )
    client.post("/api/tables/orders/records", json={"values": {"id": 1, "customer": "Alice", "status": "paid", "total": 100.0}})
    client.post("/api/tables/orders/records", json={"values": {"id": 2, "customer": "Bob", "status": "pending", "total": 50.0}})
    client.post("/api/tables/orders/records", json={"values": {"id": 3, "customer": "Charlie", "status": "paid", "total": 200.0}})

    # Test preview endpoint
    res_prev = client.post(
        "/api/views/preview",
        json={"name": "test", "sql": "SELECT customer, total FROM orders WHERE status = 'paid'"},
    )
    assert res_prev.status_code == 200
    assert res_prev.json()["total"] == 2

    # Reject view creation with invalid SQL
    res_invalid = client.post(
        "/api/views",
        json={"name": "Bad View", "sql": "SELECT non_existent_column FROM non_existent_table"},
    )
    assert res_invalid.status_code == 400

    # Reject view with empty name or sql
    assert client.post("/api/views", json={"name": "", "sql": "SELECT 1"}).status_code == 400
    assert client.post("/api/views", json={"name": "Good Name", "sql": ""}).status_code == 400

    # Create valid view
    res_create = client.post(
        "/api/views",
        json={
            "name": "Paid Orders",
            "sql": "SELECT customer, total FROM orders WHERE status = 'paid'",
            "description": "All completed transactions",
        },
    )
    assert res_create.status_code == 201
    view_data = res_create.json()
    view_id = view_data["id"]
    assert view_data["name"] == "Paid Orders"
    assert view_data["db_path"] == os.path.abspath(temp_db_path)

    # List views
    res_list = client.get("/api/views")
    assert res_list.status_code == 200
    views = res_list.json()
    assert len(views) == 1
    assert views[0]["id"] == view_id

    # Get single view
    res_get = client.get(f"/api/views/{view_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == view_id

    # Query view records
    res_records = client.get(f"/api/views/{view_id}/records?sort_by=total&sort_dir=desc")
    assert res_records.status_code == 200
    rec_data = res_records.json()
    assert rec_data["total"] == 2
    assert rec_data["records"][0]["customer"] == "Charlie"
    assert rec_data["records"][0]["total"] == 200.0
    assert rec_data["records"][1]["customer"] == "Alice"

    # Search within view records
    res_search = client.get(f"/api/views/{view_id}/records?search=Alice")
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 1
    assert res_search.json()["records"][0]["customer"] == "Alice"

    # Update view
    res_upd = client.put(
        f"/api/views/{view_id}",
        json={"name": "Completed Orders", "description": "Updated description"},
    )
    assert res_upd.status_code == 200
    assert res_upd.json()["name"] == "Completed Orders"
    assert res_upd.json()["description"] == "Updated description"

    # Delete view
    res_del = client.delete(f"/api/views/{view_id}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"

    # Confirm deleted
    assert client.get(f"/api/views/{view_id}").status_code == 404
    assert len(client.get("/api/views").json()) == 0

    client.post("/api/connection/close")

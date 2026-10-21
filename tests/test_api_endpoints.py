"""Integration tests for all API endpoints of vg-data-visor."""
import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

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


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_fs_browse():
    res = client.get("/api/fs/browse")
    assert res.status_code == 200
    data = res.json()
    assert "current_path" in data
    assert "items" in data
    assert isinstance(data["items"], list)

    # Browsing with a file path should resolve to the parent directory
    this_file = str(Path(__file__).resolve())
    res_file = client.get(f"/api/fs/browse?path={this_file}")
    assert res_file.status_code == 200
    data_file = res_file.json()
    assert data_file["current_path"] == str(Path(__file__).parent.resolve())


def test_static_spa_serving():
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "vg-data-visor" in res_root.text
    assert 'id="views-list"' in res_root.text
    assert 'id="btn-modal-create-view"' in res_root.text
    assert 'id="modal-custom-view"' in res_root.text
    assert 'id="btn-sql-save-as-view"' in res_root.text
    assert 'id="btn-select-engine-mongo"' in res_root.text
    assert 'id="container-engine-mongo"' in res_root.text
    assert 'id="form-mongo-params"' in res_root.text
    assert 'id="form-mongo-uri"' in res_root.text

    res_css = client.get("/css/semantic.min.css")
    assert res_css.status_code == 200

    res_js = client.get("/js/jquery.min.js")
    assert res_js.status_code == 200

    res_app = client.get("/js/app.js")
    assert res_app.status_code == 200
    assert "vg-data-visor" in res_app.text


def test_sql_console_terminal_assets():
    # The terminal-style SQL console relies on vendored CodeMirror assets, so the
    # page must reference them and they must be served locally (100% offline).
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "sql-terminal" in res_index.text
    assert 'id="sql-query-input"' in res_index.text

    for asset in (
        "/css/codemirror.min.css",
        "/css/codemirror-theme-dracula.min.css",
        "/js/codemirror.min.js",
        "/js/codemirror-mode-sql.min.js",
    ):
        res_asset = client.get(asset)
        assert res_asset.status_code == 200, asset
        assert len(res_asset.content) > 0


def test_rename_table_api(temp_db_path):
    # Create DB + table
    assert client.post("/api/connection/create", json={"path": temp_db_path}).status_code == 200
    client.post(
        "/api/tables/create",
        json={
            "name": "articles",
            "columns": [
                {"name": "id", "type": "INTEGER", "is_pk": True, "auto_increment": True},
                {"name": "title", "type": "TEXT"},
            ],
        },
    )
    client.post("/api/tables/articles/records", json={"values": {"title": "Book"}})

    # Rename succeeds
    res = client.post("/api/tables/articles/rename", json={"new_name": "posts"})
    assert res.status_code == 200
    assert res.json()["new_name"] == "posts"

    names = [t["name"] for t in client.get("/api/tables").json()]
    assert names == ["posts"]
    assert client.get("/api/tables/posts/records").json()["total"] == 1

    # Duplicate name is rejected with 400
    client.post(
        "/api/tables/create",
        json={"name": "drafts", "columns": [{"name": "id", "type": "INTEGER", "is_pk": True}]},
    )
    res_dup = client.post("/api/tables/posts/rename", json={"new_name": "drafts"})
    assert res_dup.status_code == 400

    # Unknown table returns 404
    res_404 = client.post("/api/tables/nope/rename", json={"new_name": "whatever"})
    assert res_404.status_code == 404

    client.post("/api/connection/close")


def test_complete_api_workflow(temp_db_path):
    # 1. Create database
    res_create_db = client.post("/api/connection/create", json={"path": temp_db_path})
    assert res_create_db.status_code == 200
    db_info = res_create_db.json()
    assert db_info["connected"] is True
    assert db_info["path"] == temp_db_path

    # Connection status
    res_status = client.get("/api/connection/status")
    assert res_status.status_code == 200
    assert res_status.json()["connected"] is True

    # Recent
    res_recent = client.get("/api/connection/recent")
    assert res_recent.status_code == 200
    assert temp_db_path in res_recent.json()

    # 2. Create table
    create_table_payload = {
        "name": "articles",
        "columns": [
            {"name": "id", "type": "INTEGER", "is_pk": True, "auto_increment": True},
            {"name": "title", "type": "TEXT", "not_null": True},
            {"name": "price", "type": "REAL", "not_null": False, "default_value": "0.0"},
        ],
    }
    res_tbl = client.post("/api/tables/create", json=create_table_payload)
    assert res_tbl.status_code == 200

    # 3. List tables
    res_tables = client.get("/api/tables")
    assert res_tables.status_code == 200
    tables = res_tables.json()
    assert len(tables) == 1
    assert tables[0]["name"] == "articles"

    # 4. Table schema
    res_schema = client.get("/api/tables/articles/schema")
    assert res_schema.status_code == 200
    schema = res_schema.json()
    assert schema["name"] == "articles"
    assert len(schema["columns"]) == 3

    # 5. Insert records
    res_ins1 = client.post("/api/tables/articles/records", json={"values": {"title": "Book", "price": 15.5}})
    assert res_ins1.status_code == 200

    res_ins2 = client.post("/api/tables/articles/records", json={"values": {"title": "Journal", "price": 3.0}})
    assert res_ins2.status_code == 200

    # 6. Read paginated records
    res_rec = client.get("/api/tables/articles/records?page=1&page_size=10")
    assert res_rec.status_code == 200
    page_data = res_rec.json()
    assert page_data["total"] == 2
    assert len(page_data["records"]) == 2

    # Search
    res_search = client.get("/api/tables/articles/records?search=Book")
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 1
    assert res_search.json()["records"][0]["title"] == "Book"

    # 7. Update record
    res_upd = client.put(
        "/api/tables/articles/records",
        json={"pk_values": {"id": 1}, "values": {"price": 18.0}},
    )
    assert res_upd.status_code == 200
    assert res_upd.json()["rows_affected"] == 1

    # 8. Add column DDL
    res_alter = client.post(
        "/api/tables/articles/alter",
        json={"column": {"name": "stock", "type": "INTEGER", "default_value": "100"}},
    )
    assert res_alter.status_code == 200

    # Verify the new column appears in records
    res_rec_after_alter = client.get("/api/tables/articles/records")
    assert "stock" in res_rec_after_alter.json()["columns"]

    # 9. SQL console
    res_q = client.post("/api/query", json={"query": "SELECT COUNT(*) as c FROM articles;"})
    assert res_q.status_code == 200
    q_data = res_q.json()
    assert q_data["row_count"] == 1
    assert q_data["rows"][0]["c"] == 2

    # 10. Delete record
    res_del = client.post("/api/tables/articles/records/delete", json={"pk_values": {"id": 2}})
    assert res_del.status_code == 200

    res_rec_after_del = client.get("/api/tables/articles/records")
    assert res_rec_after_del.json()["total"] == 1

    # 11. Drop table (DROP)
    res_drop = client.delete("/api/tables/articles/drop")
    assert res_drop.status_code == 200

    assert len(client.get("/api/tables").json()) == 0

    # 12. Close connection
    res_close = client.post("/api/connection/close")
    assert res_close.status_code == 200
    assert client.get("/api/connection/status").json()["connected"] is False

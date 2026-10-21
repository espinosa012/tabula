from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest

from backend.app.core.manager import db_manager
from backend.app.core.views_store import views_store
from backend.app.main import app

client = TestClient(app)


@patch("backend.app.api.connection.PostgreSQLDataSource.test_connection")
def test_api_postgres_test_connection_success(mock_test):
    mock_test.return_value = {
        "success": True,
        "message": "Connection OK",
        "server_version": "PostgreSQL 16.2",
        "database": "testdb",
    }

    payload = {
        "mode": "params",
        "params": {
            "host": "localhost",
            "port": 5432,
            "database": "testdb",
            "user": "postgres",
            "password": "secret",
            "sslmode": "prefer",
        },
    }
    res = client.post("/api/connection/postgres/test", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["server_version"] == "PostgreSQL 16.2"
    assert data["database"] == "testdb"


@patch("backend.app.api.connection.PostgreSQLDataSource.test_connection")
def test_api_postgres_test_connection_failure(mock_test):
    mock_test.side_effect = Exception("password authentication failed for user 'postgres'")

    payload = {
        "mode": "uri",
        "uri": "postgresql://postgres:bad@localhost:5432/testdb",
    }
    res = client.post("/api/connection/postgres/test", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert "password authentication failed" in data["message"]


@patch("backend.app.adapters.postgres.psycopg.connect")
def test_api_postgres_connect_success(mock_connect):
    mock_conn = MagicMock()
    mock_conn.closed = False
    mock_conn.info.host = "localhost"
    mock_conn.info.port = 5432
    mock_conn.info.dbname = "mydb"
    mock_conn.info.user = "myuser"

    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = (1024,)
    mock_cur.fetchall.return_value = []

    mock_connect.return_value = mock_conn

    payload = {
        "mode": "params",
        "params": {
            "host": "localhost",
            "port": 5432,
            "database": "mydb",
            "user": "myuser",
            "password": "",
            "sslmode": "prefer",
        },
    }

    res = client.post("/api/connection/postgres/connect", json=payload)
    assert res.status_code == 200
    info = res.json()
    assert info["connected"] is True
    assert info["db_type"] == "postgres"
    assert info["database"] == "mydb"
    assert info["host"] == "localhost"

    # Status check
    res_status = client.get("/api/connection/status")
    assert res_status.status_code == 200
    assert res_status.json()["connected"] is True

    # Close connection
    res_close = client.post("/api/connection/close")
    assert res_close.status_code == 200
    assert not db_manager.is_connected()


def test_views_store_with_postgres_db_id():
    pg_id = "postgres://postgres@localhost:5432/analytics"
    v = views_store.create_view(
        name="Active Users",
        sql="SELECT * FROM users WHERE active = true",
        description="Filter active users",
        db_path=pg_id,
    )
    assert v.db_path == pg_id

    # Filter by pg_id
    matched = views_store.list_views(db_path=pg_id)
    assert any(item.id == v.id for item in matched)

    # Filter by different path should not return it
    diff_matched = views_store.list_views(db_path="/tmp/other.sqlite")
    assert not any(item.id == v.id for item in diff_matched)

    # Clean up created view
    views_store.delete_view(v.id)

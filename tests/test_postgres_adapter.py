from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
import uuid
import pytest

from backend.app.adapters.postgres import (
    PostgreSQLDataSource,
    _quote_ident,
    _serialize_pg_value,
)
from backend.app.core.models import (
    ColumnDefinition,
    CreateTableRequest,
    PaginationParams,
)


def test_quote_ident():
    assert _quote_ident("users") == '"users"'
    assert _quote_ident('user"name') == '"user""name"'


def test_serialize_pg_value():
    assert _serialize_pg_value(None) is None
    assert _serialize_pg_value(123) == 123
    assert _serialize_pg_value("hello") == "hello"

    # UUID
    u = uuid.uuid4()
    assert _serialize_pg_value(u) == str(u)

    # Decimal
    d = Decimal("123.45")
    assert _serialize_pg_value(d) == 123.45

    # Datetime and Date
    now = datetime(2026, 10, 20, 15, 30, tzinfo=timezone.utc)
    assert _serialize_pg_value(now) == now.isoformat()
    d_obj = date(2026, 10, 20)
    assert _serialize_pg_value(d_obj) == "2026-10-20"

    # Bytes
    b = b"hello\x00world"
    assert _serialize_pg_value(b) == b.hex()

    # Nested structures
    nested = {
        "id": u,
        "amount": d,
        "tags": [u, Decimal("10.0")],
    }
    serialized = _serialize_pg_value(nested)
    assert serialized["id"] == str(u)
    assert serialized["amount"] == 123.45
    assert serialized["tags"] == [str(u), 10.0]


@patch("backend.app.adapters.postgres.psycopg.connect")
def test_test_connection_success(mock_connect):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = ("PostgreSQL 16.0", "testdb")
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_connect.return_value = mock_conn

    res = PostgreSQLDataSource.test_connection(host="localhost", database="testdb")
    assert res["success"] is True
    assert res["database"] == "testdb"
    assert "PostgreSQL 16.0" in res["server_version"]


@patch("backend.app.adapters.postgres.psycopg.connect")
def test_postgres_adapter_connect_and_info(mock_connect):
    mock_conn = MagicMock()
    mock_conn.closed = False
    mock_conn.info.host = "localhost"
    mock_conn.info.port = 5432
    mock_conn.info.dbname = "mydb"
    mock_conn.info.user = "myuser"

    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_connect.return_value = mock_conn

    ds = PostgreSQLDataSource()
    assert not ds.is_connected()

    # Connect via URI
    info = ds.connect("postgresql://myuser:secret@localhost:5432/mydb")
    assert ds.is_connected()
    assert info.db_type == "postgres"
    assert info.database == "mydb"
    assert info.host == "localhost"

    ds.close()
    assert not ds.is_connected()


@patch("backend.app.adapters.postgres.psycopg.connect")
def test_postgres_adapter_list_and_schema(mock_connect):
    mock_conn = MagicMock()
    mock_conn.closed = False
    mock_conn.info.host = "localhost"
    mock_conn.info.port = 5432
    mock_conn.info.dbname = "mydb"
    mock_conn.info.user = "myuser"
    mock_connect.return_value = mock_conn

    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    ds = PostgreSQLDataSource()
    ds.connect("postgresql://myuser:secret@localhost:5432/mydb")

    # Mock list_collections
    mock_cur.fetchall.return_value = [
        {"table_name": "users", "table_type": "BASE TABLE"},
        {"table_name": "v_users", "table_type": "VIEW"},
    ]
    mock_cur.fetchone.return_value = (42,)

    collections = ds.list_collections()
    assert len(collections) == 2
    assert collections[0].name == "users"
    assert collections[0].type == "table"
    assert collections[1].name == "v_users"
    assert collections[1].type == "view"

    # Mock get_schema
    # 1. table existence check
    mock_cur.fetchone.return_value = {"table_type": "BASE TABLE"}
    # 2. pk rows
    # 3. column rows
    mock_cur.fetchall.side_effect = [
        [{"column_name": "id"}],  # PKs
        [
            {
                "column_name": "id",
                "data_type": "integer",
                "is_nullable": "NO",
                "column_default": "nextval('users_id_seq'::regclass)",
                "identity_generation": None,
            },
            {
                "column_name": "name",
                "data_type": "varchar",
                "is_nullable": "YES",
                "column_default": None,
                "identity_generation": None,
            },
        ],
    ]

    schema = ds.get_schema("users")
    assert schema.name == "users"
    assert schema.pk_columns == ["id"]
    assert len(schema.columns) == 2
    assert schema.columns[0].auto_increment is True
    assert schema.columns[0].is_pk is True
    assert schema.columns[1].is_pk is False


@patch("backend.app.adapters.postgres.psycopg.connect")
def test_postgres_adapter_records_and_ctid(mock_connect):
    mock_conn = MagicMock()
    mock_conn.closed = False
    mock_conn.info.host = "localhost"
    mock_conn.info.port = 5432
    mock_conn.info.dbname = "mydb"
    mock_conn.info.user = "myuser"
    mock_connect.return_value = mock_conn

    ds = PostgreSQLDataSource()
    ds.connect("postgresql://myuser:secret@localhost:5432/mydb")

    # Table without PK
    with patch.object(ds, "get_schema") as mock_get_schema:
        from backend.app.core.models import TableSchema
        mock_get_schema.return_value = TableSchema(
            name="logs",
            type="table",
            columns=[
                ColumnDefinition(name="msg", type="TEXT"),
            ],
            pk_columns=[],
        )

        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = {"total": 1}
        mock_cur.fetchall.return_value = [
            {"_rowid_": "(0,1)", "msg": "System start"}
        ]

        res = ds.get_records("logs", PaginationParams(page=1, page_size=10))
        assert res.total == 1
        assert "_rowid_" in res.columns
        assert res.records[0]["_rowid_"] == "(0,1)"

        # Update with _rowid_
        mock_cur.fetchone.return_value = {"_rowid_": "(0,1)", "msg": "System ready"}
        updated = ds.update_record("logs", {"_rowid_": "(0,1)"}, {"msg": "System ready"})
        assert updated["msg"] == "System ready"

        # Delete with _rowid_
        mock_cur.rowcount = 1
        deleted = ds.delete_record("logs", {"_rowid_": "(0,1)"})
        assert deleted is True


@patch("backend.app.adapters.postgres.psycopg.connect")
def test_postgres_adapter_ddl_and_query(mock_connect):
    mock_conn = MagicMock()
    mock_conn.closed = False
    mock_conn.info.host = "localhost"
    mock_conn.info.port = 5432
    mock_conn.info.dbname = "mydb"
    mock_conn.info.user = "myuser"
    mock_connect.return_value = mock_conn

    ds = PostgreSQLDataSource()
    ds.connect("postgresql://myuser:secret@localhost:5432/mydb")

    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Create table
    req = CreateTableRequest(
        name="items",
        columns=[
            ColumnDefinition(name="id", type="INTEGER", is_pk=True, auto_increment=True),
            ColumnDefinition(name="data", type="BLOB"),
        ],
    )
    assert ds.create_table(req) is True

    # Alter table
    col = ColumnDefinition(name="price", type="NUMERIC")
    assert ds.add_column("items", col) is True

    # Rename table
    assert ds.rename_table("items", "products") is True

    # Execute query
    mock_cur.description = [("val",), ("name",)]
    mock_cur.fetchall.return_value = [(1, "item1")]
    q_res = ds.execute_query("SELECT 1 as val, 'item1' as name;")
    assert q_res.row_count == 1
    assert q_res.rows[0]["name"] == "item1"


@patch("backend.app.adapters.postgres.psycopg.connect")
def test_get_query_records_is_read_only_single_statement(mock_connect):
    mock_conn = MagicMock()
    mock_conn.closed = False
    mock_cur = MagicMock()
    mock_cur.description = [("name",)]
    mock_cur.fetchone.return_value = (1,)
    mock_cur.fetchall.return_value = [("100%",)]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_connect.return_value = mock_conn

    ds = PostgreSQLDataSource()
    ds.connect(host="localhost", database="db")
    mock_cur.execute.reset_mock()

    page = ds.get_query_records(
        "SELECT name FROM t WHERE name LIKE '%x'", PaginationParams(search="a")
    )
    assert page.records == [{"name": "100%"}]

    # Everything runs inside one transaction opened before the view query.
    mock_conn.transaction.assert_called_once()
    calls = mock_cur.execute.call_args_list
    assert calls[0].args[0] == "SET TRANSACTION READ ONLY;"

    # Every view statement binds parameters (extended protocol: one statement
    # per call) and escapes literal "%" so psycopg does not treat it as a placeholder.
    for call in calls[1:]:
        statement, params = call.args
        assert params, statement
        assert "LIKE '%%x'" in statement

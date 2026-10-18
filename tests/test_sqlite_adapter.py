"""Unit tests for SQLiteDataSource (connection, DDL, DML, and queries)."""
import os
import tempfile
import pytest

from backend.app.adapters.sqlite import SQLiteDataSource
from backend.app.core.models import (
    ColumnDefinition,
    CreateTableRequest,
    PaginationParams,
)


@pytest.fixture
def temp_db():
    """Create a clean temporary database for tests."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    # Remove it to test create_database
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_create_and_connect(temp_db):
    ds = SQLiteDataSource()
    assert not ds.is_connected()

    # Create a new DB
    info = ds.create_database(temp_db)
    assert info.connected
    assert info.path == temp_db
    assert ds.is_connected()

    # Close and reconnect
    ds.close()
    assert not ds.is_connected()

    reconnect_info = ds.connect(temp_db)
    assert reconnect_info.connected
    assert reconnect_info.path == temp_db


def test_table_ddl_and_schema(temp_db):
    ds = SQLiteDataSource()
    ds.create_database(temp_db)

    # Create table 'users'
    req = CreateTableRequest(
        name="users",
        columns=[
            ColumnDefinition(name="id", type="INTEGER", is_pk=True, auto_increment=True),
            ColumnDefinition(name="name", type="TEXT", not_null=True),
            ColumnDefinition(name="email", type="TEXT", not_null=False),
        ],
    )
    assert ds.create_table(req)

    # List tables
    tables = ds.list_collections()
    assert len(tables) == 1
    assert tables[0].name == "users"
    assert tables[0].type == "table"

    # Inspect schema
    schema = ds.get_schema("users")
    assert schema.name == "users"
    assert len(schema.columns) == 3
    assert schema.columns[0].name == "id"
    assert schema.columns[0].is_pk
    assert schema.columns[1].name == "name"
    assert schema.columns[1].not_null

    # Add column 'active'
    new_col = ColumnDefinition(name="active", type="INTEGER", default_value="1")
    assert ds.add_column("users", new_col)

    schema_updated = ds.get_schema("users")
    assert len(schema_updated.columns) == 4
    assert schema_updated.columns[3].name == "active"


def test_rename_table(temp_db):
    ds = SQLiteDataSource()
    ds.create_database(temp_db)

    req = CreateTableRequest(
        name="customers",
        columns=[
            ColumnDefinition(name="id", type="INTEGER", is_pk=True, auto_increment=True),
            ColumnDefinition(name="name", type="TEXT", not_null=True),
        ],
    )
    ds.create_table(req)
    ds.insert_record("customers", {"name": "Alice"})

    # Rename keeps the data and reflects the new name in the catalog/schema
    assert ds.rename_table("customers", "clients")
    assert [t.name for t in ds.list_collections()] == ["clients"]
    assert ds.get_schema("clients").name == "clients"

    page = ds.get_records("clients", PaginationParams())
    assert page.total == 1
    assert page.records[0]["name"] == "Alice"

    # A colliding target name is rejected
    ds.create_table(
        CreateTableRequest(
            name="orders",
            columns=[ColumnDefinition(name="id", type="INTEGER", is_pk=True)],
        )
    )
    with pytest.raises(ValueError):
        ds.rename_table("clients", "orders")

    # An unknown source table raises KeyError
    with pytest.raises(KeyError):
        ds.rename_table("missing_table", "whatever")


def test_table_dml_operations(temp_db):
    ds = SQLiteDataSource()
    ds.create_database(temp_db)

    # Create table
    req = CreateTableRequest(
        name="products",
        columns=[
            ColumnDefinition(name="id", type="INTEGER", is_pk=True, auto_increment=True),
            ColumnDefinition(name="name", type="TEXT", not_null=True),
            ColumnDefinition(name="price", type="REAL", not_null=True),
        ],
    )
    ds.create_table(req)

    # Insert rows
    res1 = ds.insert_record("products", {"name": "Keyboard", "price": 49.99})
    assert res1["status"] == "created"
    assert res1["lastrowid"] == 1

    res2 = ds.insert_record("products", {"name": "Mouse", "price": 19.99})
    assert res2["lastrowid"] == 2

    # Read paginated
    page = ds.get_records("products", PaginationParams(page=1, page_size=10))
    assert page.total == 2
    assert len(page.records) == 2
    assert page.records[0]["name"] == "Keyboard"

    # Search
    search_page = ds.get_records("products", PaginationParams(search="Mou"))
    assert search_page.total == 1
    assert search_page.records[0]["name"] == "Mouse"

    # Update row
    update_res = ds.update_record("products", {"id": 1}, {"price": 45.00})
    assert update_res["rows_affected"] == 1

    check_page = ds.get_records("products", PaginationParams(search="Keyboard"))
    assert check_page.records[0]["price"] == 45.00

    # Delete row
    deleted = ds.delete_record("products", {"id": 2})
    assert deleted

    page_after_delete = ds.get_records("products", PaginationParams())
    assert page_after_delete.total == 1


def test_execute_query_and_drop(temp_db):
    ds = SQLiteDataSource()
    ds.create_database(temp_db)

    # Run DDL directly
    q_create = ds.execute_query("CREATE TABLE notes (id INTEGER PRIMARY KEY, text TEXT);")
    assert "success" in q_create.message

    # Insert via query
    ds.execute_query("INSERT INTO notes (text) VALUES ('Note 1'), ('Note 2');")

    # Select via query
    q_select = ds.execute_query("SELECT * FROM notes ORDER BY id DESC;")
    assert q_select.row_count == 2
    assert len(q_select.rows) == 2
    assert q_select.rows[0]["text"] == "Note 2"

    # Drop table
    assert ds.drop_table("notes")
    assert len(ds.list_collections()) == 0

"""Unit tests for the MongoDB adapter using mongomock."""
from datetime import datetime
from decimal import Decimal

import mongomock
import pytest
from bson import ObjectId
from bson.binary import Binary
from bson.decimal128 import Decimal128

import backend.app.adapters.mongo as mongo_module
from backend.app.adapters.mongo import (
    MongoDataSource,
    _coerce_value,
    _serialize_mongo_value,
)
from backend.app.core.models import ColumnDefinition, CreateTableRequest, PaginationParams


@pytest.fixture
def mongo_source(monkeypatch):
    """A connected MongoDataSource backed by an in-memory mongomock client."""
    client = mongomock.MongoClient()
    monkeypatch.setattr(mongo_module, "MongoClient", lambda *args, **kwargs: client)
    source = MongoDataSource()
    source.connect(host="localhost", port=27017, database="testdb")
    source._db["users"].insert_many(
        [
            {"name": "Alice", "age": 30, "active": True, "tags": ["admin", "staff"]},
            {"name": "Bob", "age": 25, "active": False},
            {"name": "Carol", "age": 41, "active": True, "address": {"city": "Madrid"}},
        ]
    )
    yield source, client
    source.close()


def test_serialize_mongo_value_bson_types():
    oid = ObjectId()
    assert _serialize_mongo_value(oid) == str(oid)
    assert _serialize_mongo_value(datetime(2026, 10, 21, 12, 0)) == "2026-10-21T12:00:00"
    assert _serialize_mongo_value(Decimal128("12.5")) == 12.5
    assert _serialize_mongo_value(Decimal("3.25")) == 3.25
    assert _serialize_mongo_value(Binary(b"abc")) == "616263"

    nested = {"id": oid, "values": [Decimal128("1.5"), {"when": datetime(2026, 1, 2)}]}
    serialized = _serialize_mongo_value(nested)
    assert serialized["id"] == str(oid)
    assert serialized["values"][0] == 1.5
    assert serialized["values"][1]["when"] == "2026-01-02T00:00:00"


def test_coerce_value_from_form_strings():
    assert _coerce_value("42", "int") == 42
    assert _coerce_value("3.14", "double") == 3.14
    assert _coerce_value("true", "bool") is True
    assert _coerce_value('{"a": 1}', "object") == {"a": 1}
    assert _coerce_value('["x", "y"]', None) == ["x", "y"]
    assert _coerce_value("plain", "string") == "plain"

    oid = ObjectId()
    assert _coerce_value(str(oid), "ObjectId", "_id") == oid
    assert _coerce_value("not-an-objectid", "string", "_id") == "not-an-objectid"


def test_test_connection_with_mongomock(monkeypatch):
    client = mongomock.MongoClient()
    monkeypatch.setattr(mongo_module, "MongoClient", lambda *args, **kwargs: client)

    result = MongoDataSource.test_connection(host="localhost", database="testdb")
    assert result["success"] is True
    assert result["database"] == "testdb"

    uri_result = MongoDataSource.test_connection(uri="mongodb://localhost:27017/otherdb")
    assert uri_result["success"] is True
    assert uri_result["database"] == "otherdb"


def test_connect_metadata(mongo_source):
    source, _ = mongo_source
    info = source.get_connection_info()
    assert info.connected is True
    assert info.db_type == "mongo"
    assert info.database == "testdb"
    assert info.host == "localhost"
    assert info.port == 27017
    assert info.path == "mongodb://localhost:27017/testdb"
    assert info.tables_count == 1


def test_connect_rejects_invalid_uri():
    source = MongoDataSource()
    with pytest.raises(ValueError):
        source.connect(path="http://localhost/db")


def test_list_collections_and_schema(mongo_source):
    source, _ = mongo_source

    collections = source.list_collections()
    assert [item.name for item in collections] == ["users"]
    assert collections[0].type == "table"
    assert collections[0].row_count == 3

    schema = source.get_schema("users")
    names = [column.name for column in schema.columns]
    assert names[0] == "_id"
    assert names == ["_id", "name", "age", "active", "tags", "address"]
    assert schema.pk_columns == ["_id"]

    by_name = {column.name: column for column in schema.columns}
    assert by_name["_id"].is_pk is True
    assert by_name["_id"].auto_increment is True
    assert by_name["name"].type == "string"
    assert by_name["age"].type == "int"
    assert by_name["active"].type == "bool"
    assert by_name["tags"].type == "array"
    assert by_name["address"].type == "object"
    assert by_name["tags"].not_null is False


def test_empty_collection_schema(mongo_source):
    source, client = mongo_source
    client["testdb"].create_collection("empty")
    schema = source.get_schema("empty")
    assert [column.name for column in schema.columns] == ["_id"]
    assert schema.columns[0].is_pk is True


def test_get_records_pagination_sort_and_search(mongo_source):
    source, _ = mongo_source

    page = source.get_records("users", PaginationParams(page=1, page_size=2))
    assert page.total == 3
    assert page.total_pages == 2
    assert len(page.records) == 2
    assert page.pk_columns == ["_id"]

    sorted_page = source.get_records(
        "users", PaginationParams(page=1, page_size=10, sort_by="name", sort_dir="desc")
    )
    assert [record["name"] for record in sorted_page.records] == ["Carol", "Bob", "Alice"]

    searched = source.get_records("users", PaginationParams(search="ALI"))
    assert searched.total == 1
    assert searched.records[0]["name"] == "Alice"

    # Searching by a valid ObjectId matches the exact document.
    alice_id = searched.records[0]["_id"]
    by_id = source.get_records("users", PaginationParams(search=alice_id))
    assert by_id.total == 1
    assert by_id.records[0]["name"] == "Alice"


def test_insert_update_and_delete_document(mongo_source):
    source, _ = mongo_source

    inserted = source.insert_record("users", {"name": "Dave", "age": "22", "active": "true"})
    assert inserted["name"] == "Dave"
    assert inserted["age"] == 22
    assert inserted["active"] is True

    updated = source.update_record(
        "users", {"_id": inserted["_id"]}, {"age": "23", "nickname": "dave"}
    )
    assert updated["age"] == 23
    assert updated["nickname"] == "dave"
    assert updated["_id"] == inserted["_id"]

    assert source.delete_record("users", {"_id": inserted["_id"]}) is True
    assert source.delete_record("users", {"_id": inserted["_id"]}) is False

    with pytest.raises(ValueError):
        source.update_record("users", {"_id": inserted["_id"]}, {})


def test_collection_ddl(mongo_source):
    source, _ = mongo_source

    assert source.create_table(CreateTableRequest(name="products", columns=[])) is True
    assert "products" in source._collection_names()

    assert source.add_column(
        "products", ColumnDefinition(name="stock", type="int", default_value="5")
    ) is True
    document = source._db["products"].find_one({})
    assert document is None  # no documents to update, but the operation is valid

    source.insert_record("products", {"name": "Widget"})
    source.add_column("products", ColumnDefinition(name="stock", type="int", default_value="7"))
    assert source._db["products"].find_one({})["stock"] == 7

    assert source.rename_table("products", "items") is True
    assert "items" in source._collection_names()
    assert "products" not in source._collection_names()

    assert source.drop_table("items") is True
    assert "items" not in source._collection_names()

    with pytest.raises(KeyError):
        source.get_schema("missing")


def test_execute_query_operations(mongo_source):
    source, _ = mongo_source

    found = source.execute_query(
        '{"collection": "users", "operation": "find", "filter": {"active": true}, "sort": {"name": 1}}'
    )
    assert found.row_count == 2
    assert [row["name"] for row in found.rows] == ["Alice", "Carol"]
    assert "execution_time_ms" in found.model_dump()

    counted = source.execute_query('{"collection": "users", "operation": "count"}')
    assert counted.rows == [{"count": 3}]

    aggregated = source.execute_query(
        '{"collection": "users", "operation": "aggregate", '
        '"pipeline": [{"$group": {"_id": "$active", "total": {"$sum": 1}}}]}'
    )
    assert aggregated.row_count == 2
    assert {row["_id"] for row in aggregated.rows} == {True, False}

    distinct = source.execute_query(
        '{"collection": "users", "operation": "distinct", "field": "active"}'
    )
    assert distinct.row_count == 2

    inserted = source.execute_query(
        '{"collection": "users", "operation": "insertOne", "document": {"name": "Eve", "age": 19}}'
    )
    assert inserted.row_count == 1
    assert "inserted _id" in inserted.message

    updated = source.execute_query(
        '{"collection": "users", "operation": "updateMany", "filter": {"active": true}, '
        '"update": {"$set": {"active": false}}}'
    )
    assert updated.row_count == 2  # Alice and Carol (Eve has no 'active' field)

    deleted = source.execute_query(
        '{"collection": "users", "operation": "deleteMany", "filter": {"active": false}}'
    )
    assert deleted.row_count >= 1

    listed = source.execute_query('{"operation": "listCollections"}')
    assert [row["name"] for row in listed.rows] == ["users"]

    with pytest.raises(RuntimeError):
        source.execute_query('{"collection": "users", "operation": "nope"}')

    with pytest.raises(RuntimeError):
        source.execute_query("not valid json")

    with pytest.raises(RuntimeError):
        source.execute_query('{"operation": "find"}')


def test_get_query_records_find_and_aggregate(mongo_source):
    source, _ = mongo_source

    find_page = source.get_query_records(
        '{"collection": "users", "filter": {"active": true}}',
        PaginationParams(page=1, page_size=1, search="a"),
    )
    assert find_page.total == 2
    assert find_page.total_pages == 2
    assert find_page.pk_columns == []

    aggregate_page = source.get_query_records(
        '{"collection": "users", "operation": "aggregate", "pipeline": []}',
        PaginationParams(page=1, page_size=2, sort_by="name", sort_dir="desc"),
    )
    assert aggregate_page.total == 3
    assert [record["name"] for record in aggregate_page.records] == ["Carol", "Bob"]

    with pytest.raises(ValueError):
        source.get_query_records(
            '{"collection": "users", "operation": "insertOne", "document": {}}',
            PaginationParams(),
        )


def test_get_query_records_aggregate_keeps_pipeline_sort(mongo_source):
    source, _ = mongo_source

    page = source.get_query_records(
        '{"collection": "users", "operation": "aggregate", '
        '"pipeline": [{"$sort": {"age": 1}}]}',
        PaginationParams(page=1, page_size=2),
    )
    assert page.total == 3
    assert [record["name"] for record in page.records] == ["Bob", "Alice"]


def test_views_store_accepts_mongo_identifier():
    from backend.app.core.views_store import views_store

    mongo_id = "mongodb://localhost:27017/analytics"
    view = views_store.create_view(
        name="Active Users",
        sql='{"collection": "users", "filter": {"active": true}}',
        db_path=mongo_id,
    )
    try:
        matched = views_store.list_views(db_path=mongo_id)
        assert any(item.id == view.id for item in matched)
        assert not any(
            item.id == view.id for item in views_store.list_views(db_path="/tmp/other.sqlite")
        )
    finally:
        views_store.delete_view(view.id)

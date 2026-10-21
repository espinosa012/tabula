"""Tests for MongoDB connection models."""
from backend.app.core.models import (
    ConnectionInfo,
    MongoConnectRequest,
    MongoConnectionParams,
    MongoTestResponse,
)


def test_mongo_connection_params_defaults():
    params = MongoConnectionParams()
    assert params.host == "localhost"
    assert params.port == 27017
    assert params.database == "test"
    assert params.auth_source == "admin"
    assert params.tls is False


def test_mongo_connect_request_params_mode():
    req = MongoConnectRequest(
        mode="params",
        params=MongoConnectionParams(host="db.local", database="analytics", tls=True),
    )
    assert req.params.host == "db.local"
    assert req.params.database == "analytics"
    assert req.params.tls is True
    assert req.uri is None


def test_mongo_connect_request_uri_mode():
    uri = "mongodb+srv://user:secret@cluster.example.net/analytics"
    req = MongoConnectRequest(mode="uri", uri=uri)
    assert req.uri == uri
    assert req.params is None


def test_mongo_test_response():
    response = MongoTestResponse(success=True, message="ok", server_version="MongoDB 7.0")
    assert response.success is True
    assert response.database is None


def test_connection_info_supports_mongo_and_port():
    info = ConnectionInfo(
        path="mongodb://localhost:27017/test",
        connected=True,
        db_type="mongo",
        database="test",
        host="localhost",
        port=27017,
    )
    assert info.db_type == "mongo"
    assert info.port == 27017

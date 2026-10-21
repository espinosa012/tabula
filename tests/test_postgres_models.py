import pytest
from backend.app.core.models import (
    ConnectionInfo,
    PostgresConnectionParams,
    PostgresConnectionUri,
    PostgresConnectRequest,
    PostgresTestResponse,
)


def test_postgres_models():
    # PostgresConnectionParams default values
    p = PostgresConnectionParams()
    assert p.host == "localhost"
    assert p.port == 5432
    assert p.database == "postgres"
    assert p.user == "postgres"
    assert p.sslmode == "prefer"

    # Custom params
    custom = PostgresConnectionParams(
        host="remote.server.com",
        port=6543,
        database="mydb",
        user="myuser",
        password="secretpassword",
        sslmode="require",
    )
    assert custom.host == "remote.server.com"
    assert custom.port == 6543
    assert custom.database == "mydb"
    assert custom.password == "secretpassword"

    # Connection URI
    uri_model = PostgresConnectionUri(uri="postgresql://user:pass@localhost:5432/mydb?sslmode=require")
    assert uri_model.uri.startswith("postgresql://")

    # Connect Request with params
    req_params = PostgresConnectRequest(mode="params", params=custom)
    assert req_params.mode == "params"
    assert req_params.params is not None
    assert req_params.params.database == "mydb"

    # Connect Request with URI
    req_uri = PostgresConnectRequest(mode="uri", uri="postgresql://localhost:5432/test")
    assert req_uri.mode == "uri"
    assert req_uri.uri == "postgresql://localhost:5432/test"

    # Extended ConnectionInfo
    info = ConnectionInfo(
        path="postgres@localhost:5432/postgres",
        connected=True,
        tables_count=5,
        db_type="postgres",
        database="postgres",
        host="localhost",
        user="postgres",
        schema_name="public",
    )
    assert info.db_type == "postgres"
    assert info.schema_name == "public"

    # Test Response
    res = PostgresTestResponse(
        success=True,
        message="Connection OK",
        server_version="PostgreSQL 16.1",
        database="mydb",
    )
    assert res.success is True
    assert res.server_version == "PostgreSQL 16.1"

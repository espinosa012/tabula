"""Tests for LocalRequestGuard (CSRF / DNS-rebinding protection)."""
from fastapi.testclient import TestClient

from backend.app.core.security import LocalRequestGuard, allowed_hosts_from_env
from backend.app.main import app

client = TestClient(app)


def _guard(hosts=("127.0.0.1", "localhost", "::1")):
    return LocalRequestGuard(app=None, allowed_hosts=hosts)


def test_same_origin_requests_are_allowed():
    assert client.get("/api/health").status_code == 200
    res = client.post(
        "/api/connection/close",
        headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"},
    )
    assert res.status_code == 200


def test_foreign_host_header_is_rejected():
    res = client.get("/api/health", headers={"Host": "evil.example.com"})
    assert res.status_code == 403
    res = client.get("/", headers={"Host": "attacker.test:8000"})
    assert res.status_code == 403


def test_cross_origin_requests_are_rejected():
    for origin in ("https://evil.example.com", "http://testserver:9999", "null"):
        res = client.post("/api/query", json={"query": "SELECT 1"}, headers={"Origin": origin})
        assert res.status_code == 403, origin


def test_cross_site_api_request_without_origin_is_rejected():
    res = client.get("/api/fs/browse", headers={"Sec-Fetch-Site": "cross-site"})
    assert res.status_code == 403
    # The UI itself can still be opened from an external link.
    assert client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


def test_no_cors_headers_are_sent():
    res = client.options(
        "/api/query",
        headers={"Origin": "http://testserver", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in res.headers


def test_reject_reason_handles_ports_and_ipv6():
    guard = _guard()
    assert guard._reject_reason({"host": "127.0.0.1:8000"}, "/api/health") is None
    assert guard._reject_reason({"host": "LOCALHOST:8000"}, "/api/health") is None
    assert guard._reject_reason({"host": "[::1]:8000"}, "/api/health") is None
    assert guard._reject_reason(
        {"host": "localhost:8000", "origin": "http://localhost:8000"}, "/api/query"
    ) is None
    assert guard._reject_reason({}, "/api/health") is not None
    assert guard._reject_reason({"host": "127.0.0.1.evil.com"}, "/api/health") is not None
    assert guard._reject_reason(
        {"host": "localhost:8000", "origin": "http://127.0.0.1:8000"}, "/api/query"
    ) is not None


def test_allowed_hosts_from_env(monkeypatch):
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("ALLOWED_HOSTS", " MyBox.local , 192.168.1.20 ")
    hosts = allowed_hosts_from_env()
    assert {"127.0.0.1", "localhost", "::1", "mybox.local", "192.168.1.20"} <= hosts
    assert "0.0.0.0" not in hosts

    monkeypatch.setenv("HOST", "10.0.0.5")
    monkeypatch.delenv("ALLOWED_HOSTS")
    assert "10.0.0.5" in allowed_hosts_from_env()

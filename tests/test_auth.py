"""Tests de la auth por API key en endpoints administrativos."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


def _make_client(monkeypatch, admin_key: str | None) -> TestClient:
    if admin_key is None:
        monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ADMIN_API_KEY", admin_key)

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)

    import importlib
    from app import config, db, auth, main
    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(auth)
    importlib.reload(main)

    db.init_db()
    return TestClient(main.app)


@pytest.fixture
def app_with_key(monkeypatch):
    yield _make_client(monkeypatch, "secret-test-key")


@pytest.fixture
def app_without_key(monkeypatch):
    yield _make_client(monkeypatch, None)


def test_no_key_required_when_unset(app_without_key):
    assert app_without_key.get("/leads").status_code == 200
    assert app_without_key.get("/kpis").status_code == 200
    assert app_without_key.get("/dashboard").status_code == 200


def test_rejects_request_without_key(app_with_key):
    assert app_with_key.get("/leads").status_code == 401
    assert app_with_key.get("/kpis").status_code == 401
    assert app_with_key.get("/dashboard").status_code == 401


def test_rejects_wrong_key(app_with_key):
    headers = {"X-Admin-API-Key": "wrong"}
    assert app_with_key.get("/leads", headers=headers).status_code == 401


def test_accepts_correct_key_header(app_with_key):
    headers = {"X-Admin-API-Key": "secret-test-key"}
    assert app_with_key.get("/leads", headers=headers).status_code == 200
    assert app_with_key.get("/kpis", headers=headers).status_code == 200


def test_accepts_correct_key_query(app_with_key):
    assert app_with_key.get("/leads?key=secret-test-key").status_code == 200
    assert app_with_key.get("/dashboard?key=secret-test-key").status_code == 200


def test_healthcheck_always_open(app_with_key):
    # El healthcheck `/` no requiere auth (lo usan load balancers)
    assert app_with_key.get("/").status_code == 200

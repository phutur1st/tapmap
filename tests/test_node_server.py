"""Tests for model/node_server.py — uses Flask test client, no real HTTP."""

from __future__ import annotations

import json
from typing import Any

import pytest
from flask import Flask

from model.node_server import register_node_endpoint


# ---------- Helpers ----------

def _make_snapshot(extra: dict | None = None) -> dict[str, Any]:
    snap: dict[str, Any] = {
        "error": False,
        "stats": {"online": True},
        "cache_items": [{"ip": "1.2.3.4", "port": 443}],
        "map_candidates": [],
        "open_ports": [],
    }
    if extra:
        snap.update(extra)
    return snap


def _make_app(snapshot_fn, token=None) -> Flask:
    app = Flask(__name__)
    register_node_endpoint(app, snapshot_fn, token=token)
    return app


# ---------- Basic response tests ----------

def test_endpoint_returns_200_and_json_snapshot() -> None:
    snap = _make_snapshot()
    app = _make_app(lambda: snap)

    with app.test_client() as client:
        resp = client.get("/api/v1/snapshot")

    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")
    data = json.loads(resp.data)
    assert data["error"] is False
    assert "cache_items" in data


def test_endpoint_strips_app_info_field() -> None:
    snap = _make_snapshot({"app_info": {"version": "1.0", "secret": "xyz"}})
    app = _make_app(lambda: snap)

    with app.test_client() as client:
        resp = client.get("/api/v1/snapshot")

    data = json.loads(resp.data)
    assert "app_info" not in data


def test_endpoint_returns_fresh_snapshot_each_call() -> None:
    counter = {"n": 0}

    def snapshot_fn() -> dict:
        counter["n"] += 1
        return _make_snapshot({"call_count": counter["n"]})

    app = _make_app(snapshot_fn)

    with app.test_client() as client:
        r1 = json.loads(client.get("/api/v1/snapshot").data)
        r2 = json.loads(client.get("/api/v1/snapshot").data)

    assert r1["call_count"] == 1
    assert r2["call_count"] == 2


def test_endpoint_returns_500_when_snapshot_raises() -> None:
    def bad_snap():
        raise RuntimeError("db gone")

    app = _make_app(bad_snap)

    with app.test_client() as client:
        resp = client.get("/api/v1/snapshot")

    assert resp.status_code == 500
    data = json.loads(resp.data)
    assert data["error"] is True
    assert "db gone" in data["message"]


# ---------- Auth tests ----------

def test_endpoint_returns_200_with_no_token_configured() -> None:
    app = _make_app(lambda: _make_snapshot(), token=None)

    with app.test_client() as client:
        resp = client.get("/api/v1/snapshot")

    assert resp.status_code == 200


def test_endpoint_returns_200_with_correct_bearer_token() -> None:
    app = _make_app(lambda: _make_snapshot(), token="my-secret")

    with app.test_client() as client:
        resp = client.get(
            "/api/v1/snapshot",
            headers={"Authorization": "Bearer my-secret"},
        )

    assert resp.status_code == 200


def test_endpoint_returns_401_with_missing_auth_header() -> None:
    app = _make_app(lambda: _make_snapshot(), token="my-secret")

    with app.test_client() as client:
        resp = client.get("/api/v1/snapshot")

    assert resp.status_code == 401
    data = json.loads(resp.data)
    assert data["error"] is True


def test_endpoint_returns_401_with_wrong_token() -> None:
    app = _make_app(lambda: _make_snapshot(), token="my-secret")

    with app.test_client() as client:
        resp = client.get(
            "/api/v1/snapshot",
            headers={"Authorization": "Bearer wrong-token"},
        )

    assert resp.status_code == 401


def test_endpoint_returns_401_with_malformed_auth_header() -> None:
    app = _make_app(lambda: _make_snapshot(), token="my-secret")

    with app.test_client() as client:
        resp = client.get(
            "/api/v1/snapshot",
            headers={"Authorization": "Basic my-secret"},
        )

    assert resp.status_code == 401


def test_endpoint_only_allows_get_method() -> None:
    app = _make_app(lambda: _make_snapshot())

    with app.test_client() as client:
        resp = client.post("/api/v1/snapshot")

    assert resp.status_code == 405

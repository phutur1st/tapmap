"""Tests for model/node_client.py — no real network access required."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from model.node_client import (
    HubPoller,
    LOCAL_NODE_NAME,
    NodeClient,
    NodeConfig,
    NodeFetchResult,
    load_nodes_config,
    results_to_status,
)


# ---------- Helpers ----------

def _make_payload(extra: dict | None = None) -> dict:
    payload = {
        "error": False,
        "stats": {"online": True},
        "cache_items": [{"ip": "1.2.3.4", "port": 443}],
        "map_candidates": [{"ip": "1.2.3.4", "port": 443, "lon": 10.0, "lat": 50.0}],
        "open_ports": [{"local_address": "0.0.0.0:80"}],
    }
    if extra:
        payload.update(extra)
    return payload


def _make_response(payload: dict) -> MagicMock:
    body = json.dumps(payload).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------- load_nodes_config ----------

def test_load_nodes_config_returns_empty_when_file_missing(tmp_path: Path) -> None:
    result = load_nodes_config(tmp_path)
    assert result == []


def test_load_nodes_config_returns_empty_for_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "nodes.json").write_text("not json", encoding="utf-8")
    assert load_nodes_config(tmp_path) == []


def test_load_nodes_config_returns_empty_for_non_array(tmp_path: Path) -> None:
    (tmp_path / "nodes.json").write_text('{"name": "x"}', encoding="utf-8")
    assert load_nodes_config(tmp_path) == []


def test_load_nodes_config_skips_entries_missing_name(tmp_path: Path) -> None:
    data = [{"url": "http://10.0.0.1:8050"}]
    (tmp_path / "nodes.json").write_text(json.dumps(data), encoding="utf-8")
    assert load_nodes_config(tmp_path) == []


def test_load_nodes_config_skips_entries_missing_url(tmp_path: Path) -> None:
    data = [{"name": "server-a"}]
    (tmp_path / "nodes.json").write_text(json.dumps(data), encoding="utf-8")
    assert load_nodes_config(tmp_path) == []


def test_load_nodes_config_parses_valid_entries(tmp_path: Path) -> None:
    data = [
        {"name": "server-a", "url": "http://10.0.0.1:8050"},
        {"name": "server-b", "url": "http://10.0.0.2:8050/"},
    ]
    (tmp_path / "nodes.json").write_text(json.dumps(data), encoding="utf-8")
    result = load_nodes_config(tmp_path)
    assert len(result) == 2
    assert result[0].name == "server-a"
    assert result[0].url == "http://10.0.0.1:8050"
    assert result[1].url == "http://10.0.0.2:8050"  # trailing slash stripped


def test_load_nodes_config_applies_global_token(tmp_path: Path) -> None:
    data = [{"name": "server-a", "url": "http://10.0.0.1:8050"}]
    (tmp_path / "nodes.json").write_text(json.dumps(data), encoding="utf-8")
    result = load_nodes_config(tmp_path, token="global-secret")
    assert result[0].token == "global-secret"


def test_load_nodes_config_entry_token_overrides_global(tmp_path: Path) -> None:
    data = [{"name": "server-a", "url": "http://10.0.0.1:8050", "token": "entry-secret"}]
    (tmp_path / "nodes.json").write_text(json.dumps(data), encoding="utf-8")
    result = load_nodes_config(tmp_path, token="global-secret")
    assert result[0].token == "entry-secret"


# ---------- NodeClient.fetch ----------

def _fake_urlopen(response_obj):
    """Return a context manager that yields response_obj."""
    return MagicMock(__enter__=lambda s: response_obj, __exit__=MagicMock(return_value=False))


def test_node_client_fetch_success() -> None:
    config = NodeConfig(name="server-a", url="http://10.0.0.1:8050")
    payload = _make_payload()

    with patch("model.node_client.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(payload)
        result = NodeClient(config).fetch()

    assert result.ok is True
    assert result.node_name == "server-a"
    assert result.payload is not None
    assert result.error_msg == ""
    assert result.latency_ms >= 0


def test_node_client_fetch_stamps_node_name_on_items() -> None:
    config = NodeConfig(name="server-a", url="http://10.0.0.1:8050")
    payload = _make_payload()

    with patch("model.node_client.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(payload)
        result = NodeClient(config).fetch()

    assert result.payload is not None
    for item in result.payload["cache_items"]:
        assert item.get("node") == "server-a"
    for item in result.payload["map_candidates"]:
        assert item.get("node") == "server-a"
    for item in result.payload["open_ports"]:
        assert item.get("node") == "server-a"


def test_node_client_fetch_adds_auth_header_when_token_set() -> None:
    config = NodeConfig(name="server-a", url="http://10.0.0.1:8050", token="secret")
    payload = _make_payload()

    captured_req: list = []

    def fake_urlopen(req, timeout):
        captured_req.append(req)
        return _make_response(payload)

    with patch("model.node_client.urllib.request.urlopen", side_effect=fake_urlopen):
        NodeClient(config).fetch()

    assert captured_req
    auth = captured_req[0].get_header("Authorization")
    assert auth == "Bearer secret"


def test_node_client_fetch_returns_failure_on_http_error() -> None:
    config = NodeConfig(name="server-a", url="http://10.0.0.1:8050")

    with patch("model.node_client.urllib.request.urlopen", side_effect=OSError("refused")):
        result = NodeClient(config).fetch()

    assert result.ok is False
    assert "refused" in result.error_msg
    assert result.payload is None


def test_node_client_fetch_returns_failure_on_invalid_json() -> None:
    config = NodeConfig(name="server-a", url="http://10.0.0.1:8050")
    bad_resp = MagicMock()
    bad_resp.read.return_value = b"not json"

    with patch("model.node_client.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response.__func__ if False else bad_resp
        bad_resp.__enter__ = lambda s: bad_resp
        bad_resp.__exit__ = MagicMock(return_value=False)
        with patch("model.node_client.urllib.request.urlopen", return_value=bad_resp):
            result = NodeClient(config).fetch()

    assert result.ok is False


def test_node_client_fetch_returns_failure_on_missing_required_keys() -> None:
    config = NodeConfig(name="server-a", url="http://10.0.0.1:8050")
    incomplete = {"error": False}  # missing required keys

    with patch("model.node_client.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(incomplete)
        result = NodeClient(config).fetch()

    assert result.ok is False


def test_node_client_fetch_injects_node_status_when_absent() -> None:
    config = NodeConfig(name="server-a", url="http://10.0.0.1:8050")
    payload = _make_payload()  # no node_status key

    with patch("model.node_client.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(payload)
        result = NodeClient(config).fetch()

    assert result.payload is not None
    assert "node_status" in result.payload
    assert result.payload["node_status"] == []


# ---------- HubPoller.fetch_all ----------

def test_hub_poller_fetch_all_returns_results_for_all_nodes() -> None:
    nodes = [
        NodeConfig(name="a", url="http://10.0.0.1:8050"),
        NodeConfig(name="b", url="http://10.0.0.2:8050"),
    ]

    with patch("model.node_client.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(_make_payload())
        results = HubPoller(nodes).fetch_all()

    assert len(results) == 2
    names = {r.node_name for r in results}
    assert names == {"a", "b"}


def test_hub_poller_fetch_all_filters_by_active_names() -> None:
    nodes = [
        NodeConfig(name="a", url="http://10.0.0.1:8050"),
        NodeConfig(name="b", url="http://10.0.0.2:8050"),
    ]

    with patch("model.node_client.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(_make_payload())
        results = HubPoller(nodes).fetch_all(active_names=["a"])

    assert len(results) == 1
    assert results[0].node_name == "a"


def test_hub_poller_fetch_all_returns_empty_for_no_targets() -> None:
    nodes = [NodeConfig(name="a", url="http://10.0.0.1:8050")]
    results = HubPoller(nodes).fetch_all(active_names=[])
    assert results == []


def test_hub_poller_fetch_all_returns_failure_when_node_raises() -> None:
    nodes = [NodeConfig(name="dead", url="http://10.0.0.99:8050")]

    with patch("model.node_client.urllib.request.urlopen", side_effect=OSError("timeout")):
        results = HubPoller(nodes).fetch_all()

    assert len(results) == 1
    assert results[0].ok is False


# ---------- results_to_status ----------

def test_results_to_status_formats_ok_result() -> None:
    result = NodeFetchResult(
        node_name="server-a",
        payload=None,
        ok=True,
        error_msg="",
        latency_ms=42.7,
        last_ok_ts="12:34:56",
    )
    status = results_to_status([result])
    assert len(status) == 1
    assert status[0]["name"] == "server-a"
    assert status[0]["ok"] is True
    assert status[0]["latency_ms"] == 43
    assert status[0]["last_ok_ts"] == "12:34:56"


def test_results_to_status_formats_failed_result() -> None:
    result = NodeFetchResult(
        node_name="server-b",
        payload=None,
        ok=False,
        error_msg="connection refused",
        latency_ms=4001.0,
    )
    status = results_to_status([result])
    assert status[0]["ok"] is False
    assert status[0]["error_msg"] == "connection refused"


def test_results_to_status_returns_empty_for_empty_input() -> None:
    assert results_to_status([]) == []

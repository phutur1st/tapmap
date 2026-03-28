"""HTTP client for polling remote TapMap node instances.

A node exposes GET /api/v1/snapshot.  A hub polls one or more nodes in
parallel and merges their SnapshotPayload data into its own.

No external dependencies — uses only stdlib urllib and concurrent.futures.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from model.model import CacheItem, SnapshotPayload

logger = logging.getLogger(__name__)

_SNAPSHOT_PATH: str = "/api/v1/snapshot"
_REQUIRED_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {"error", "stats", "cache_items", "map_candidates", "open_ports"}
)

LOCAL_NODE_NAME: str = "__local__"


@dataclass(frozen=True)
class NodeConfig:
    """Store connection details for one remote node."""

    name: str
    url: str
    token: str | None = None


@dataclass
class NodeFetchResult:
    """Store the outcome of one node poll attempt."""

    node_name: str
    payload: SnapshotPayload | None
    ok: bool
    error_msg: str
    latency_ms: float
    last_ok_ts: str = field(default="")


class NodeClient:
    """Fetch a snapshot from a single remote TapMap node."""

    def __init__(self, config: NodeConfig, timeout_s: float = 4.0) -> None:
        self._config = config
        self._timeout = timeout_s

    def fetch(self) -> NodeFetchResult:
        """Fetch and return a stamped SnapshotPayload from the node."""
        url = self._config.url.rstrip("/") + _SNAPSHOT_PATH
        t0 = time.monotonic()

        try:
            req = urllib.request.Request(url)
            if self._config.token:
                req.add_header("Authorization", f"Bearer {self._config.token}")

            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()

            latency_ms = (time.monotonic() - t0) * 1000
            payload = self._parse_and_stamp(raw)

            logger.debug(
                "Node %s: fetched %.0f ms, %d cache_items",
                self._config.name,
                latency_ms,
                len(payload["cache_items"]),
            )
            return NodeFetchResult(
                node_name=self._config.name,
                payload=payload,
                ok=True,
                error_msg="",
                latency_ms=latency_ms,
                last_ok_ts=_now_ts(),
            )

        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning("Node %s: fetch failed — %s", self._config.name, exc)
            return NodeFetchResult(
                node_name=self._config.name,
                payload=None,
                ok=False,
                error_msg=str(exc),
                latency_ms=latency_ms,
            )

    def _parse_and_stamp(self, raw: bytes) -> SnapshotPayload:
        """Parse JSON response and stamp node name onto every item."""
        data = json.loads(raw)

        if not isinstance(data, dict):
            raise ValueError("Node response is not a JSON object")

        missing = _REQUIRED_PAYLOAD_KEYS - data.keys()
        if missing:
            raise ValueError(f"Node response missing keys: {missing}")

        name = self._config.name

        for item in data.get("cache_items", []):
            if isinstance(item, dict):
                item["node"] = name

        for item in data.get("map_candidates", []):
            if isinstance(item, dict):
                item["node"] = name

        for item in data.get("open_ports", []):
            if isinstance(item, dict):
                item["node"] = name

        if "node_status" not in data:
            data["node_status"] = []

        return data  # type: ignore[return-value]


class HubPoller:
    """Poll multiple nodes in parallel and return their results."""

    def __init__(self, nodes: list[NodeConfig], timeout_s: float = 4.0) -> None:
        self._nodes = nodes
        self._timeout = timeout_s

    def fetch_all(self, active_names: list[str] | None = None) -> list[NodeFetchResult]:
        """Fetch all nodes (or a subset) in parallel.

        Args:
            active_names: If provided, only fetch nodes whose name is in this
                list.  Pass None to fetch all configured nodes.

        Returns:
            List of NodeFetchResult in completion order.
        """
        targets = [
            n for n in self._nodes
            if active_names is None or n.name in active_names
        ]

        if not targets:
            return []

        results: list[NodeFetchResult] = []

        with ThreadPoolExecutor(max_workers=len(targets), thread_name_prefix="hub-poll") as ex:
            futures = {ex.submit(NodeClient(n, self._timeout).fetch): n for n in targets}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    node = futures[future]
                    results.append(NodeFetchResult(
                        node_name=node.name,
                        payload=None,
                        ok=False,
                        error_msg=str(exc),
                        latency_ms=0.0,
                    ))

        return results


def load_nodes_config(data_dir: Path, token: str | None = None) -> list[NodeConfig]:
    """Read nodes.json from data_dir and return a list of NodeConfig.

    Returns an empty list if the file is absent or invalid.
    Each entry may specify its own token; if absent, the global token is used.

    Expected format::

        [
          {"name": "server-a", "url": "http://192.168.1.10:8050"},
          {"name": "server-b", "url": "http://192.168.1.11:8050", "token": "override"}
        ]
    """
    path = Path(data_dir) / "nodes.json"
    if not path.is_file():
        return []

    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("nodes.json could not be read: %s", exc)
        return []

    if not isinstance(entries, list):
        logger.warning("nodes.json: expected a JSON array, got %s", type(entries).__name__)
        return []

    configs: list[NodeConfig] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        url = entry.get("url")
        if not isinstance(name, str) or not name:
            logger.warning("nodes.json: entry missing 'name', skipping: %s", entry)
            continue
        if not isinstance(url, str) or not url:
            logger.warning("nodes.json: entry missing 'url', skipping: %s", entry)
            continue
        entry_token = entry.get("token") or token
        configs.append(NodeConfig(name=name, url=url.rstrip("/"), token=entry_token))

    return configs


def results_to_status(results: list[NodeFetchResult]) -> list[dict[str, Any]]:
    """Convert fetch results to a JSON-serializable status list for the UI."""
    return [
        {
            "name": r.node_name,
            "ok": r.ok,
            "error_msg": r.error_msg,
            "latency_ms": round(r.latency_ms),
            "last_ok_ts": r.last_ok_ts,
        }
        for r in results
    ]


def _now_ts() -> str:
    """Return current local time as HH:MM:SS."""
    from datetime import datetime

    return datetime.now().strftime("%H:%M:%S")

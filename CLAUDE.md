# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TapMap is a network connection visualization tool that monitors local TCP/UDP connections, enriches IPs with MaxMind GeoLite2 geolocation data, and displays them on an interactive Plotly map via a Dash web app. Runs entirely locally at `127.0.0.1:8050`.

## Commands

```bash
# Run the app
python tapmap.py

# Run tests
pytest
pytest tests/test_modal.py                    # single file
pytest tests/test_modal.py::test_decide_close  # single test

# Lint and format
ruff check .
ruff format .

# Build executable (PyInstaller)
python tools/build.py

# Docker (Linux only)
docker compose -f compose.linux.yaml up --build
```

## Architecture

**Data flow:** Socket data (lsof/psutil) → `Model.snapshot()` → GeoInfo enrichment → `StatusCache` → UI rendering (Dash/Plotly)

### Key layers

- **`tapmap.py`** — Entry point. Dash app setup and callback wiring. Delegates decisions to `state/` and rendering to `ui/`.

- **`model/`** — Data collection and enrichment.
  - `netinfo.py` — Protocol-based facade selecting platform backend.
  - `netinfo_lsof.py` — macOS backend (parses `lsof` output).
  - `netinfo_psutil.py` — Windows/Linux backend.
  - `geoinfo.py` — MaxMind GeoIP enrichment with LRU cache.
  - `model.py` — `Model.snapshot()` orchestrates collection + enrichment, returns typed `SnapshotPayload`.

- **`state/`** — Pure decision logic, **no Dash imports**. This makes all state transitions directly unit-testable without mocking Dash.
  - `status_cache.py` — Accumulates unique sockets/services across polls.
  - `modal.py`, `keyboard.py`, `menu.py`, `poll.py` — State transition functions.

- **`ui/`** — Rendering helpers that produce Dash components.
  - `map_view.py` — Plotly choropleth map figure.
  - `modal_view.py`, `cache_view.py` — Modal and table content builders.
  - `layout_view.py` — Main layout structure.

- **`assets/`** — Frontend: `styles.css` (dark theme, `#00ff66` accent), `keys.js` (keyboard event handler).

### Hub-Node multi-instance mode

TapMap supports a hub-node topology where one "hub" instance aggregates connections from multiple remote "node" instances.

- **Node** (`TAPMAP_NODE_MODE=1`): exposes `GET /api/v1/snapshot` on the existing Dash server.  No extra port needed.
- **Hub** (a `nodes.json` file present in the data directory): polls all configured nodes in parallel on every tick and merges their data into the map.
- **Single instance** (default): behavior is identical to before — node/hub features are off unless explicitly configured.

**`nodes.json`** — place in the same data directory as `.mmdb` files:
```json
[
  {"name": "server-a", "url": "http://192.168.1.10:8050"},
  {"name": "server-b", "url": "http://192.168.1.11:8050"}
]
```

**Node selector** (hub only): toggle buttons in the menu panel switch between Local / individual nodes / All.  The full cache is kept in memory — toggling a node back on restores its points instantly.

**Per-node colors**: each node gets a distinct color from the `NODE_COLORS` palette in `ui/map_view.py`.

**Status bar** shows `NODES: {ok}/{total}` when hub mode is active.

### Platform backends

macOS uses `lsof`, Windows/Linux use `psutil`. The `NetInfoBackend` protocol in `netinfo.py` abstracts this. Docker requires `--network host --pid host`.

## Conventions

- **Python 3.10+** — Uses `match` statements, modern type hints, `from __future__ import annotations`.
- **Ruff** — Line length 100, Google-style docstrings. Rules: `E, F, I, B, UP, SIM, RUF, D`.
- **TypedDict payloads** — `CacheItem`, `OpenPort`, `SnapshotPayload` for structured data between layers.
- **Data directory** — Platform-specific (`~/Library/Application Support/TapMap` on macOS, `%APPDATA%\TapMap` on Windows, `~/.local/share/TapMap` on Linux). Must contain `GeoLite2-City.mmdb` and `GeoLite2-ASN.mmdb`.

## Environment Variables

```
TAPMAP_PORT       — Override server port (default 8050)
TAPMAP_HOST       — Override bind host (default 127.0.0.1)
TAPMAP_DATA_DIR   — Override data directory path
TAPMAP_IN_DOCKER  — Signal Docker mode (sets host to 0.0.0.0)

MAXMIND_ACCOUNT_ID            — MaxMind account ID (enables auto-update)
MAXMIND_LICENSE_KEY           — MaxMind license key (enables auto-update)
MAXMIND_UPDATE_INTERVAL_DAYS  — Refresh cadence in days (default 7)

TAPMAP_NODE_MODE  — Set to "1" to enable the /api/v1/snapshot node endpoint
TAPMAP_NODE_TOKEN — Shared Bearer token for hub→node authentication (optional)
```

When `MAXMIND_ACCOUNT_ID` and `MAXMIND_LICENSE_KEY` are set, TapMap automatically
downloads and refreshes `GeoLite2-City.mmdb` and `GeoLite2-ASN.mmdb` into the data
directory on startup and on the configured interval. Without credentials, databases
must be placed manually as before.

When `nodes.json` is present in the data directory, the instance acts as a hub and
polls the listed nodes on every tick. Set `TAPMAP_NODE_TOKEN` on both hub and node
instances to require Bearer token authentication on the snapshot endpoint.

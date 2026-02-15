"""
Configuration for TapMap.

Users can edit this file to adjust basic behaviour
without modifying the application code.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final, Literal

# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

def _get_base_dir() -> Path:
    """
    Base directory for TapMap.

    - Source run: directory containing config.py
    - PyInstaller exe: directory containing the executable
    """
    if getattr(sys, "frozen", False):
        # Running as PyInstaller executable
        return Path(sys.executable).resolve().parent
    # Running from source
    return Path(__file__).resolve().parent


# Base directory of the project or executable
BASE_DIR: Final[Path] = _get_base_dir()

# Directory containing GeoLite2 databases
GEO_DATA_DIR: Final[Path] = BASE_DIR / "data"


# ---------------------------------------------------------------------
# Local map marker
# ---------------------------------------------------------------------

# Type for location setting
LocationMode = Literal["auto", "none"]

# Local map marker:
# - (lon, lat): fixed manual location
# - "auto": approximate location based on public IP
# - "none": no local marker
# MY_LOCATION: Final[tuple[float, float] | LocationMode] = (11.3421, 59.5950)
MY_LOCATION: Final[tuple[float, float] | LocationMode] = "auto"
# MY_LOCATION: Final[tuple[float, float] | LocationMode] = "none"


# ---------------------------------------------------------------------
# Polling and map behaviour
# ---------------------------------------------------------------------

# Snapshot interval in milliseconds
POLL_INTERVAL_MS: Final[int] = 5_000

# Decimal precision for grouping endpoints on the map
# 3 ≈ 100 m precision
COORD_PRECISION: Final[int] = 3

# Distance threshold for marking endpoints as "nearby"
# Endpoints closer than this distance are shown in yellow.
ZOOM_NEAR_KM: Final[float] = 25.0

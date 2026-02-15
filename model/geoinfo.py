"""
GeoInfo enriches connection records with GeoIP and ASN information using MaxMind databases.

Expected files in the configured data_dir:
- GeoLite2-City.mmdb
- GeoLite2-ASN.mmdb

If the database files are missing or cannot be opened, GeoInfo will operate in
disabled mode and attach None values for geo fields.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypedDict

import maxminddb


class GeoResult(TypedDict):
    lat: float | None
    lon: float | None
    city: str | None
    country: str | None
    asn: int | None
    asn_org: str | None


_EMPTY_RESULT: Final[GeoResult] = {
    "lat": None,
    "lon": None,
    "city": None,
    "country": None,
    "asn": None,
    "asn_org": None,
}


@dataclass(frozen=True)
class GeoDbPaths:
    """File paths to the MaxMind databases."""

    city_db: Path
    asn_db: Path


class GeoInfo:
    """
    Enrich connections with geo and ASN details based on raddr_ip.

    This class is best effort:
    - If DB files are missing, it will not raise by default.
    - Lookup results are cached per IP to reduce repeated DB reads.

    The enrich() method mutates the dictionaries in the provided list by adding:
    lat, lon, city, country, asn, asn_org.
    """

    CITY_DB_NAME: Final[str] = "GeoLite2-City.mmdb"
    ASN_DB_NAME: Final[str] = "GeoLite2-ASN.mmdb"

    def __init__(
        self,
        data_dir: Path,
        *,
        cache_size: int = 10_000,
        silent: bool = True,
    ) -> None:
        """
        Args:
            data_dir: Directory containing GeoLite2 mmdb files.
            cache_size: Maximum number of IP lookup results to keep in memory (LRU).
            silent: If False, raises on DB open errors. If True, runs in disabled mode.
        """
        self._cache_size = max(0, int(cache_size))
        self._silent = bool(silent)

        data_dir = Path(data_dir)
        self._paths = GeoDbPaths(
            city_db=data_dir / self.CITY_DB_NAME,
            asn_db=data_dir / self.ASN_DB_NAME,
        )

        self._city_reader: maxminddb.Reader | None = None
        self._asn_reader: maxminddb.Reader | None = None

        self._cache: OrderedDict[str, GeoResult] = OrderedDict()

        self._open_readers()

    @property
    def paths(self) -> GeoDbPaths:
        """Return the configured DB paths."""
        return self._paths

    @property
    def enabled(self) -> bool:
        """True when at least one DB reader is available."""
        return (self._city_reader is not None) or (self._asn_reader is not None)

    def _open_readers(self) -> None:
        """Open MaxMind DB readers. If silent=True, failures disable enrichment."""
        try:
            if self._paths.city_db.is_file():
                self._city_reader = maxminddb.open_database(self._paths.city_db)
        except Exception:
            if not self._silent:
                raise

        try:
            if self._paths.asn_db.is_file():
                self._asn_reader = maxminddb.open_database(self._paths.asn_db)
        except Exception:
            if not self._silent:
                raise

    def enrich(self, connections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Enrich each connection dict in-place using raddr_ip.

        Args:
            connections: List of connection dictionaries. Expected key: "raddr_ip".

        Returns:
            The same list object, enriched in-place.
        """
        if not isinstance(connections, list) or not connections:
            return connections

        if not self.enabled:
            return connections

        for conn in connections:
            if not isinstance(conn, dict):
                continue

            ip = conn.get("raddr_ip")
            if not isinstance(ip, str) or not ip:
                continue

            geo = self.lookup(ip)

            conn["lat"] = geo["lat"]
            conn["lon"] = geo["lon"]
            conn["city"] = geo["city"]
            conn["country"] = geo["country"]
            conn["asn"] = geo["asn"]
            conn["asn_org"] = geo["asn_org"]

        return connections

    def lookup(self, ip: str) -> GeoResult:
        """
        Lookup geo information for an IP address.

        Returns:
            GeoResult with possible None values.
        """
        if not ip:
            return dict(_EMPTY_RESULT)

        cached = self._cache_get(ip)
        if cached is not None:
            return dict(cached)

        result: GeoResult = dict(_EMPTY_RESULT)

        if self._city_reader is not None:
            self._fill_city(ip, result)

        if self._asn_reader is not None:
            self._fill_asn(ip, result)

        self._cache_put(ip, result)
        return result

    def _fill_city(self, ip: str, result: GeoResult) -> None:
        """Fill city-related fields into result if available."""
        try:
            city = self._city_reader.get(ip) if self._city_reader is not None else None
        except Exception:
            return

        if not isinstance(city, dict):
            return

        loc = city.get("location")
        if isinstance(loc, dict):
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            result["lat"] = float(lat) if isinstance(lat, (int, float)) else None
            result["lon"] = float(lon) if isinstance(lon, (int, float)) else None

        city_block = city.get("city")
        if isinstance(city_block, dict):
            names = city_block.get("names")
            if isinstance(names, dict):
                name = names.get("en")
                result["city"] = name if isinstance(name, str) and name else None

        country_block = city.get("country")
        if isinstance(country_block, dict):
            names = country_block.get("names")
            if isinstance(names, dict):
                name = names.get("en")
                result["country"] = name if isinstance(name, str) and name else None

    def _fill_asn(self, ip: str, result: GeoResult) -> None:
        """Fill ASN-related fields into result if available."""
        try:
            asn = self._asn_reader.get(ip) if self._asn_reader is not None else None
        except Exception:
            return

        if not isinstance(asn, dict):
            return

        asn_num = asn.get("autonomous_system_number")
        result["asn"] = int(asn_num) if isinstance(asn_num, int) else None

        org = asn.get("autonomous_system_organization")
        result["asn_org"] = org if isinstance(org, str) and org else None

    def _cache_get(self, ip: str) -> GeoResult | None:
        """Return cached value and refresh LRU order."""
        if self._cache_size <= 0:
            return None
        val = self._cache.get(ip)
        if val is None:
            return None
        self._cache.move_to_end(ip, last=True)
        return val

    def _cache_put(self, ip: str, result: GeoResult) -> None:
        """Insert into cache and evict least-recently-used items if needed."""
        if self._cache_size <= 0:
            return
        self._cache[ip] = result
        self._cache.move_to_end(ip, last=True)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def close(self) -> None:
        """Close any open MaxMind DB readers."""
        if self._city_reader is not None:
            self._city_reader.close()
            self._city_reader = None
        if self._asn_reader is not None:
            self._asn_reader.close()
            self._asn_reader = None

    def __enter__(self) -> "GeoInfo":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

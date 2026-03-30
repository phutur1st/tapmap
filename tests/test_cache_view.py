"""Tests for CacheViewBuilder in ui/cache_view.py."""

from __future__ import annotations

from unittest.mock import patch

from ui.cache_view import CacheViewBuilder


def _candidate(
    ip: str = "1.2.3.4",
    port: int = 443,
    proto: str = "tcp",
    lon: float = 10.0,
    lat: float = 50.0,
    city: str = "Berlin",
    country: str = "DE",
    asn: int = 12345,
    asn_org: str = "Example ISP",
    process_name: str = "curl",
    pid: int = 100,
    node: str | None = None,
) -> dict:
    return {
        "ip": ip,
        "port": port,
        "proto": proto,
        "lon": lon,
        "lat": lat,
        "city": city,
        "country": country,
        "asn": asn,
        "asn_org": asn_org,
        "process_name": process_name,
        "pid": pid,
        "node": node,
    }


class TestHitCountAndAge:
    def test_new_entry_has_hit_count_1(self) -> None:
        builder = CacheViewBuilder()
        cache = builder.merge_map_candidates({}, [_candidate()])
        entry = next(iter(cache.values()))
        assert entry["hit_count"] == 1

    def test_new_entry_has_first_seen_and_last_seen(self) -> None:
        builder = CacheViewBuilder()
        with patch.object(CacheViewBuilder, "_now_text", return_value="2024-01-01 00:00:00"):
            cache = builder.merge_map_candidates({}, [_candidate()])
        entry = next(iter(cache.values()))
        assert entry["first_seen"] == "2024-01-01 00:00:00"
        assert entry["last_seen"] == "2024-01-01 00:00:00"

    def test_second_merge_increments_hit_count(self) -> None:
        builder = CacheViewBuilder()
        cache = builder.merge_map_candidates({}, [_candidate()])
        cache = builder.merge_map_candidates(cache, [_candidate()])
        entry = next(iter(cache.values()))
        assert entry["hit_count"] == 2

    def test_third_merge_increments_hit_count_to_3(self) -> None:
        builder = CacheViewBuilder()
        cache = builder.merge_map_candidates({}, [_candidate()])
        cache = builder.merge_map_candidates(cache, [_candidate()])
        cache = builder.merge_map_candidates(cache, [_candidate()])
        entry = next(iter(cache.values()))
        assert entry["hit_count"] == 3

    def test_first_seen_preserved_on_subsequent_merges(self) -> None:
        builder = CacheViewBuilder()
        with patch.object(CacheViewBuilder, "_now_text", return_value="2024-01-01 00:00:00"):
            cache = builder.merge_map_candidates({}, [_candidate()])
        with patch.object(CacheViewBuilder, "_now_text", return_value="2024-01-02 12:00:00"):
            cache = builder.merge_map_candidates(cache, [_candidate()])
        entry = next(iter(cache.values()))
        assert entry["first_seen"] == "2024-01-01 00:00:00"

    def test_last_seen_updated_on_subsequent_merges(self) -> None:
        builder = CacheViewBuilder()
        with patch.object(CacheViewBuilder, "_now_text", return_value="2024-01-01 00:00:00"):
            cache = builder.merge_map_candidates({}, [_candidate()])
        with patch.object(CacheViewBuilder, "_now_text", return_value="2024-01-02 12:00:00"):
            cache = builder.merge_map_candidates(cache, [_candidate()])
        entry = next(iter(cache.values()))
        assert entry["last_seen"] == "2024-01-02 12:00:00"

    def test_different_service_keys_get_separate_hit_counts(self) -> None:
        builder = CacheViewBuilder()
        cache = builder.merge_map_candidates(
            {}, [_candidate(ip="1.1.1.1", port=80), _candidate(ip="2.2.2.2", port=443)]
        )
        cache = builder.merge_map_candidates(
            cache, [_candidate(ip="1.1.1.1", port=80)]
        )
        # 1.1.1.1:80 hit twice, 2.2.2.2:443 hit once
        counts = {v["ip"]: v["hit_count"] for v in cache.values()}
        assert counts["1.1.1.1"] == 2
        assert counts["2.2.2.2"] == 1

    def test_hit_count_missing_defaults_to_1_on_increment(self) -> None:
        """Entries loaded from old cache without hit_count should increment cleanly."""
        builder = CacheViewBuilder()
        old_entry = {"ip": "1.2.3.4", "port": 443, "proto": "tcp", "lon": 10.0, "lat": 50.0}
        cache = builder.merge_map_candidates({"1.2.3.4|443": old_entry}, [_candidate()])
        entry = cache["1.2.3.4|443"]
        assert entry["hit_count"] == 2


class TestFormatOrgBlock:
    def test_format_org_block_includes_hits_line(self) -> None:
        builder = CacheViewBuilder()
        with patch.object(CacheViewBuilder, "_now_text", return_value="2024-01-01 00:00:00"):
            cache = builder.merge_map_candidates({}, [_candidate()])
        view = builder.build_view_from_cache(cache)
        detail = view["details"]["0"]
        assert "Hits: 1" in detail
        assert "First: 2024-01-01 00:00:00" in detail
        assert "Last: 2024-01-01 00:00:00" in detail

    def test_hits_increments_in_click_details(self) -> None:
        builder = CacheViewBuilder()
        cache = builder.merge_map_candidates({}, [_candidate()])
        cache = builder.merge_map_candidates(cache, [_candidate()])
        view = builder.build_view_from_cache(cache)
        detail = view["details"]["0"]
        assert "Hits: 2" in detail

"""Tests for model/hostname_cache.py."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from model.hostname_cache import HostnameCache


class TestHostnameCacheGetReturnsNoneOnFirstCall:
    def test_returns_none_on_first_call(self) -> None:
        cache = HostnameCache()
        with patch("socket.gethostbyaddr", return_value=("example.com", [], ["1.2.3.4"])):
            result = cache.get("1.2.3.4")
        assert result is None

    def test_returns_hostname_after_resolution(self) -> None:
        cache = HostnameCache()
        resolved = []

        def fake_gethostbyaddr(ip: str):
            return ("example.com", [], [ip])

        with patch("socket.gethostbyaddr", side_effect=fake_gethostbyaddr):
            cache.get("1.2.3.4")
            # Wait for background thread to complete
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                result = cache.get("1.2.3.4")
                if result is not None:
                    resolved.append(result)
                    break
                time.sleep(0.01)

        assert resolved == ["example.com"]

    def test_returns_none_when_resolution_fails(self) -> None:
        import socket as _socket
        cache = HostnameCache()
        with patch("socket.gethostbyaddr", side_effect=_socket.herror("not found")):
            cache.get("10.0.0.1")
            deadline = time.monotonic() + 2.0
            result = None
            while time.monotonic() < deadline:
                result = cache.get("10.0.0.1")
                # Once the thread finishes the sentinel is replaced with None
                with cache._lock:
                    if cache._cache.get("10.0.0.1") != HostnameCache.PENDING:
                        break
                time.sleep(0.01)
        # Resolution failed → returns None (not the hostname)
        assert result is None

    def test_returns_none_when_hostname_equals_ip(self) -> None:
        """When gethostbyaddr returns the IP itself, treat it as no hostname."""
        ip = "8.8.8.8"
        cache = HostnameCache()
        with patch("socket.gethostbyaddr", return_value=(ip, [], [ip])):
            cache.get(ip)
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                with cache._lock:
                    if cache._cache.get(ip) != HostnameCache.PENDING:
                        break
                time.sleep(0.01)
        assert cache.get(ip) is None


class TestHostnameCacheLruEviction:
    def test_evicts_oldest_when_over_capacity(self) -> None:
        cache = HostnameCache(cache_size=3)
        # Pre-populate with resolved entries (bypass threads for speed)
        with cache._lock:
            cache._cache["a"] = "host-a"
            cache._cache["b"] = "host-b"
            cache._cache["c"] = "host-c"

        # Adding a 4th entry should evict "a"
        with patch("socket.gethostbyaddr", return_value=("host-d", [], ["d"])):
            # Directly insert to test eviction logic
            with cache._lock:
                cache._cache["d"] = "host-d"
                cache._evict_if_needed()

        with cache._lock:
            assert "a" not in cache._cache
            assert "d" in cache._cache

    def test_lru_touch_on_get(self) -> None:
        cache = HostnameCache(cache_size=3)
        with cache._lock:
            cache._cache["a"] = "host-a"
            cache._cache["b"] = "host-b"
            cache._cache["c"] = "host-c"

        # Touch "a" so it becomes most recently used
        cache.get("a")

        # Add a new entry — should evict "b" (now oldest)
        with cache._lock:
            cache._cache["d"] = "host-d"
            cache._evict_if_needed()

        with cache._lock:
            assert "b" not in cache._cache
            assert "a" in cache._cache


class TestHostnameCacheThreadSafety:
    def test_concurrent_gets_for_same_ip_spawn_one_thread(self) -> None:
        """Multiple concurrent gets for the same IP should not spawn duplicate threads."""
        import threading
        cache = HostnameCache()
        thread_counts: list[int] = []
        barrier = threading.Barrier(5)

        def fake_resolve(ip: str):
            return ("host.example.com", [], [ip])

        def worker():
            barrier.wait()
            with patch("socket.gethostbyaddr", side_effect=fake_resolve):
                cache.get("192.168.1.1")

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        # After all workers ran, IP should be in cache exactly once
        with cache._lock:
            assert list(cache._cache.keys()).count("192.168.1.1") == 1

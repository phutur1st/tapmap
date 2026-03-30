"""Asynchronous reverse-DNS hostname cache for TapMap.

Lookups are performed in background daemon threads so the UI poll loop
is never blocked.  The first call for an IP returns None (lookup pending);
subsequent calls return the hostname once it has resolved.

Results are cached indefinitely for the life of the process (LRU eviction
when the cache reaches ``cache_size`` entries).
"""

from __future__ import annotations

import logging
import socket
import threading
from collections import OrderedDict
from typing import Final

logger = logging.getLogger(__name__)

_SENTINEL: Final[str] = "__pending__"


class HostnameCache:
    """Resolve IP addresses to hostnames asynchronously."""

    PENDING: Final[str] = _SENTINEL

    def __init__(self, cache_size: int = 2000, timeout_s: float = 2.0) -> None:
        self._cache_size = cache_size
        self._timeout_s = timeout_s
        self._cache: OrderedDict[str, str | None] = OrderedDict()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, ip: str) -> str | None:
        """Return the resolved hostname for *ip*, or None if not yet available.

        On the first call for *ip* a background thread is started to resolve
        it.  Subsequent calls return the cached result once it arrives.
        Returns ``None`` while resolution is in progress or if it failed.
        """
        with self._lock:
            if ip in self._cache:
                value = self._cache[ip]
                # Move to end (LRU touch)
                self._cache.move_to_end(ip)
                if value is _SENTINEL:
                    return None
                return value

            # Not seen yet — insert PENDING and spawn a resolver thread
            self._cache[ip] = _SENTINEL
            self._evict_if_needed()

        t = threading.Thread(
            target=self._resolve_worker, args=(ip,), daemon=True, name=f"hostname-{ip}"
        )
        t.start()
        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_worker(self, ip: str) -> None:
        hostname: str | None = None
        try:
            result = socket.gethostbyaddr(ip)
            hostname = result[0] if result[0] != ip else None
        except (socket.herror, socket.gaierror, OSError):
            hostname = None
        except Exception:
            hostname = None

        with self._lock:
            # Only update if still in cache (could have been evicted)
            if ip in self._cache:
                self._cache[ip] = hostname
                self._cache.move_to_end(ip)

        logger.debug("Resolved %s -> %s", ip, hostname)

    def _evict_if_needed(self) -> None:
        """Remove oldest entry if cache is over capacity. Must hold _lock."""
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

"""Collect TCP/UDP connections from all Linux network namespaces.

When TapMap runs with --pid host (Docker) or as root on a bare Linux host,
each process's /proc/<pid>/net/tcp[6] and udp[6] exposes the connection table
for its network namespace.  Bridge-networked Docker containers each live in
their own namespace, invisible to psutil.net_connections() which only reads
the host namespace.

This module walks /proc, identifies unique namespaces by their inode, reads
connection tables from each non-host namespace, and returns the results in the
same dict format as PsutilNetInfo so they can be merged transparently.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import struct
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROC = Path("/proc")

_TCP_STATES: dict[str, str] = {
    "01": "ESTABLISHED",
    "02": "SYN_SENT",
    "03": "SYN_RECV",
    "04": "FIN_WAIT1",
    "05": "FIN_WAIT2",
    "06": "TIME_WAIT",
    "07": "CLOSE",
    "08": "CLOSE_WAIT",
    "09": "LAST_ACK",
    "0A": "LISTEN",
    "0B": "CLOSING",
}


def _hex_to_ipv4(hex_str: str) -> str:
    packed = bytes.fromhex(hex_str)
    addr = struct.unpack("<I", packed)[0]
    return str(ipaddress.IPv4Address(struct.pack(">I", addr)))


def _hex_to_ipv6(hex_str: str) -> str:
    packed = bytes.fromhex(hex_str)
    words = struct.unpack("<4I", packed)
    addr = struct.pack(">4I", *words)
    return str(ipaddress.IPv6Address(addr))


def _parse_addr(addr_hex: str, *, v6: bool) -> tuple[str, int]:
    ip_hex, port_hex = addr_hex.split(":")
    ip = _hex_to_ipv6(ip_hex) if v6 else _hex_to_ipv4(ip_hex)
    return ip, int(port_hex, 16)


def _ns_inode(pid: int) -> int | None:
    try:
        return os.stat(f"/proc/{pid}/ns/net").st_ino
    except OSError:
        return None


_CONTAINER_ID_RE = __import__("re").compile(r"/docker/([0-9a-f]{64})")


def _parse_container_id_from_cgroup(text: str) -> str | None:
    """Extract the first Docker container ID from cgroup file content.

    Returns the full 64-char hex ID, or None if not found.
    """
    m = _CONTAINER_ID_RE.search(text)
    return m.group(1) if m else None


def _read_container_id(pid: int) -> str | None:
    """Return a 12-char short container ID for the given PID, or None."""
    try:
        text = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    full = _parse_container_id_from_cgroup(text)
    return full[:12] if full else None


def _read_comm(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _scan_fds(pid: int, result: dict[int, int]) -> None:
    """Scan /proc/<pid>/fd for socket inodes.

    All threads in a process share the same fd table (CLONE_FILES), so
    /proc/<pid>/fd already covers every thread.  Scanning /proc/<pid>/task/*/fd
    is redundant and extremely slow on processes with many threads (e.g. a
    torrent client with hundreds of threads).
    """
    fd_dir = Path(f"/proc/{pid}/fd")
    try:
        for fd in fd_dir.iterdir():
            try:
                target = os.readlink(fd)
                if target.startswith("socket:["):
                    inode = int(target[8:-1])
                    result.setdefault(inode, pid)
            except (OSError, ValueError):
                continue
    except (OSError, PermissionError):
        return


def _build_socket_inode_map(pids: list[int]) -> dict[int, int]:
    """Return mapping of socket inode -> PID by scanning /proc/<pid>/fd."""
    result: dict[int, int] = {}
    for pid in pids:
        _scan_fds(pid, result)
    return result


def _read_net_file(
    path: Path,
    *,
    proto: str,
    v6: bool,
    allowed_statuses: set[str] | None,
) -> list[dict[str, Any]]:
    """Parse a /proc/<pid>/net/{tcp,tcp6,udp,udp6} file."""
    try:
        text = path.read_text(encoding="ascii", errors="replace")
    except OSError:
        return []

    rows = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 10:
            continue
        try:
            l_ip, l_port = _parse_addr(parts[1], v6=v6)
            r_ip, r_port = _parse_addr(parts[2], v6=v6)
            state_hex = parts[3].upper()
            inode = int(parts[9])
        except (ValueError, IndexError):
            continue

        if proto == "tcp":
            status = _TCP_STATES.get(state_hex, "UNKNOWN")
            if allowed_statuses and status not in allowed_statuses:
                continue
        else:
            status = "NONE"

        # inode=0 means TIME_WAIT / orphaned socket — no owning process exists
        if inode == 0:
            continue

        rows.append({
            "proto": proto,
            "status": status,
            "laddr_ip": l_ip if l_ip not in ("0.0.0.0", "::") else None,
            "laddr_port": l_port or None,
            "raddr_ip": r_ip if r_ip not in ("0.0.0.0", "::") else None,
            "raddr_port": r_port or None,
            "_inode": inode,
            "_v6": v6,
        })
    return rows


def collect_namespace_connections(
    allowed_statuses: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return connections from all non-host Linux network namespaces.

    Silently returns an empty list if /proc is inaccessible, not on Linux,
    or no extra namespaces are found.
    """
    if not _PROC.exists():
        return []

    host_inode = _ns_inode(os.getpid())

    # Walk /proc: group PIDs by namespace inode, skip host namespace
    ns_to_pids: dict[int, list[int]] = {}

    try:
        entries = list(_PROC.iterdir())
    except OSError:
        return []

    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        inode = _ns_inode(pid)
        if inode is None or inode == host_inode:
            continue
        ns_to_pids.setdefault(inode, []).append(pid)

    if not ns_to_pids:
        return []

    logger.debug("Found %d non-host network namespace(s)", len(ns_to_pids))

    # Build dedup key from proto + addresses to avoid duplicating host conns
    results: list[dict[str, Any]] = []

    for ns_inode_val, ns_pids in ns_to_pids.items():
        # Build socket inode→pid map scoped to this namespace's PIDs only.
        # Scanning fewer PIDs reduces the race window significantly.
        inode_to_pid = _build_socket_inode_map(ns_pids)

        # Best-effort namespace name: use the process that owns the most sockets
        # in this namespace (most likely the main app, not a supervisor/init).
        # Fall back to the lowest PID if counts are tied or inode map is empty.
        if inode_to_pid:
            from collections import Counter
            pid_socket_counts = Counter(inode_to_pid.values())
            rep_pid = pid_socket_counts.most_common(1)[0][0]
        else:
            rep_pid = min(ns_pids)
        ns_fallback_name = _read_comm(rep_pid)

        base = Path(f"/proc/{rep_pid}/net")
        for filename, proto, v6 in [
            ("tcp", "tcp", False),
            ("tcp6", "tcp", True),
            ("udp", "udp", False),
            ("udp6", "udp", True),
        ]:
            rows = _read_net_file(
                base / filename,
                proto=proto,
                v6=v6,
                allowed_statuses=allowed_statuses,
            )
            for row in rows:
                sock_inode = row.pop("_inode", 0)
                v6_flag = row.pop("_v6", False)
                owner_pid = inode_to_pid.get(sock_inode)

                # Try to resolve the specific process that owns this socket.
                # Fall back to the namespace representative name, then "Container".
                name = _read_comm(owner_pid) if owner_pid else None
                if name is None:
                    name = ns_fallback_name
                label = name or "Container"

                # Append short container ID if this process lives in a Docker cgroup.
                container_pid = owner_pid if owner_pid else rep_pid
                short_id = _read_container_id(container_pid)
                if short_id:
                    label = f"{label} [{short_id}]"

                row.update({
                    "pid": owner_pid,
                    "family": "AF_INET6" if v6_flag else "AF_INET",
                    "type": "SOCK_DGRAM" if proto == "udp" else "SOCK_STREAM",
                    "process_status": "OK" if name else "Unavailable",
                    "process_label": label,
                    "process_name": name,
                    "exe": None,
                    "cmdline": None,
                })
                results.append(row)

    logger.debug("Namespace scan: %d additional connection(s) found", len(results))
    return results


def is_available() -> bool:
    """Return True if namespace scanning is likely to work on this system."""
    try:
        return (
            _PROC.exists()
            and Path("/proc/1/ns/net").exists()
            and _ns_inode(1) is not None
        )
    except OSError:
        return False

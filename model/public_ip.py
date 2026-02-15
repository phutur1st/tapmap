"""
Public IP lookup utilities.

This module resolves the machine's public IP address using a small external
service. The result is validated as an IPv4 or IPv6 address.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Final
from urllib.error import URLError
from urllib.request import urlopen


LOGGER = logging.getLogger(__name__)

IPIFY_URL: Final[str] = "https://api.ipify.org"


def get_public_ip(*, timeout_s: float = 2.0) -> str | None:
    """
    Return the public IP address of the current machine.

    The function queries a lightweight external service.
    Returns None if the IP cannot be resolved or validated.

    Args:
        timeout_s: Request timeout in seconds.

    Returns:
        Public IP address as a string, or None on failure.
    """
    try:
        with urlopen(IPIFY_URL, timeout=timeout_s) as resp:
            raw_ip = resp.read().decode("utf-8").strip()
    except URLError as exc:
        LOGGER.debug("Public IP lookup failed: %s", exc)
        return None

    try:
        ipaddress.ip_address(raw_ip)
    except ValueError:
        LOGGER.debug("Public IP lookup returned invalid IP: %r", raw_ip)
        return None

    return raw_ip

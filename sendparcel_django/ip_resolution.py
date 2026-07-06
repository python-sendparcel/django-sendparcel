"""Trusted-proxy-aware source-IP resolution for webhook callbacks."""

from __future__ import annotations

import ipaddress
from typing import Any

from sendparcel.logging import get_logger

from sendparcel_django.conf import get_settings

logger = get_logger(__name__)


def resolve_client_ip(meta: dict[str, Any]) -> str:
    """Resolve the real client IP from request META, respecting trusted proxies.

    When ``SENDPARCEL_TRUSTED_PROXIES`` is configured and ``REMOTE_ADDR``
    falls within a trusted network, walk ``X-Forwarded-For``
    **right-to-left**, skipping trusted-proxy hops, and return the first
    **untrusted** address (the real client).  When
    ``SENDPARCEL_TRUSTED_PROXIES`` is empty or unset, return
    ``REMOTE_ADDR`` unchanged — backward compatible with current behaviour.

    Never trusts the left-most XFF value (client-controlled / spoofable).

    Args:
        meta: ``request.META`` dict from a Django HttpRequest.

    Returns:
        The resolved client IP address string.
    """
    remote_addr = meta.get("REMOTE_ADDR", "")

    trusted_proxies = get_settings().TRUSTED_PROXIES

    if not trusted_proxies:
        # No trusted proxies configured — use REMOTE_ADDR directly.
        return remote_addr

    # Build network objects from SENDPARCEL_TRUSTED_PROXIES.
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for cidr in trusted_proxies:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            # A typo here silently weakens webhook IP verification —
            # skip the entry but say so.
            logger.warning(
                "Ignoring malformed SENDPARCEL_TRUSTED_PROXIES entry: %r",
                cidr,
            )
            continue

    def _is_trusted(ip_str: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip_str)
            return any(addr in net for net in networks)
        except ValueError:
            return False

    if not _is_trusted(remote_addr):
        # REMOTE_ADDR is not a trusted proxy — return as-is.
        return remote_addr

    # REMOTE_ADDR is trusted — resolve X-Forwarded-For right-to-left.
    xff = meta.get("HTTP_X_FORWARDED_FOR", "")
    if not xff:
        return remote_addr

    # Walk right-to-left, skip trusted hops, return first untrusted.
    for ip in reversed(xff.split(",")):
        cleaned = ip.strip()
        if cleaned and not _is_trusted(cleaned):
            return cleaned

    # All XFF entries are trusted proxies — fall back to REMOTE_ADDR.
    return remote_addr

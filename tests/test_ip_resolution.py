"""Tests for trusted-proxy-aware source-IP resolution."""

from __future__ import annotations

import logging

import pytest
from django.test import override_settings
from sendparcel_django.ip_resolution import resolve_client_ip


class TestResolveClientIp:
    """Tests for resolve_client_ip."""

    def test_no_trusted_proxies_returns_remote_addr(self) -> None:
        """Without TRUSTED_PROXIES, REMOTE_ADDR is returned as-is."""
        meta = {"REMOTE_ADDR": "203.0.113.50"}
        assert resolve_client_ip(meta) == "203.0.113.50"

    @override_settings(SENDPARCEL_TRUSTED_PROXIES=[])
    def test_empty_trusted_proxies_returns_remote_addr(self) -> None:
        """Empty TRUSTED_PROXIES list = no proxy resolution."""
        meta = {
            "REMOTE_ADDR": "10.0.0.1",
            "HTTP_X_FORWARDED_FOR": "203.0.113.50",
        }
        assert resolve_client_ip(meta) == "10.0.0.1"

    @override_settings(SENDPARCEL_TRUSTED_PROXIES=["10.0.0.0/8"])
    def test_untrusted_remote_addr_returns_remote_addr(self) -> None:
        """REMOTE_ADDR not in trusted range → no XFF resolution."""
        meta = {
            "REMOTE_ADDR": "203.0.113.50",
            "HTTP_X_FORWARDED_FOR": "192.168.1.1",
        }
        assert resolve_client_ip(meta) == "203.0.113.50"

    @override_settings(SENDPARCEL_TRUSTED_PROXIES=["10.0.0.0/8"])
    def test_trusted_proxy_resolves_xff_right_to_left(self) -> None:
        """Trusted REMOTE_ADDR walks XFF right-to-left, returns first
        untrusted address."""
        meta = {
            "REMOTE_ADDR": "10.0.0.1",
            # Left-most is spoofable; right-most is the real client.
            "HTTP_X_FORWARDED_FOR": "192.168.1.100,203.0.113.50",
        }
        assert resolve_client_ip(meta) == "203.0.113.50"

    @override_settings(SENDPARCEL_TRUSTED_PROXIES=["10.0.0.0/8"])
    def test_skips_trusted_hops_in_xff(self) -> None:
        """Skip trusted-proxy hops in XFF chain."""
        meta = {
            "REMOTE_ADDR": "10.0.0.1",
            # 10.0.0.5 is also trusted; 203.0.113.50 is real client.
            "HTTP_X_FORWARDED_FOR": "192.168.1.100,10.0.0.5,203.0.113.50",
        }
        assert resolve_client_ip(meta) == "203.0.113.50"

    @override_settings(SENDPARCEL_TRUSTED_PROXIES=["10.0.0.0/8"])
    def test_spoofed_xff_from_untrusted_remote_is_ignored(self) -> None:
        """Untrusted REMOTE_ADDR can't inject carrier IP via XFF."""
        meta = {
            "REMOTE_ADDR": "192.168.1.100",  # Not trusted
            "HTTP_X_FORWARDED_FOR": "91.216.25.10",  # Spoofed carrier IP
        }
        assert resolve_client_ip(meta) == "192.168.1.100"

    @override_settings(SENDPARCEL_TRUSTED_PROXIES=["10.0.0.0/8"])
    def test_no_xff_header_returns_remote_addr(self) -> None:
        """No XFF header → fall back to REMOTE_ADDR even if trusted."""
        meta = {
            "REMOTE_ADDR": "10.0.0.1",
        }
        assert resolve_client_ip(meta) == "10.0.0.1"

    @override_settings(SENDPARCEL_TRUSTED_PROXIES=["10.0.0.0/8"])
    def test_empty_xff_header_returns_remote_addr(self) -> None:
        """Empty XFF header → fall back to REMOTE_ADDR."""
        meta = {
            "REMOTE_ADDR": "10.0.0.1",
            "HTTP_X_FORWARDED_FOR": "",
        }
        assert resolve_client_ip(meta) == "10.0.0.1"

    @override_settings(SENDPARCEL_TRUSTED_PROXIES=["10.0.0.0/8"])
    def test_all_xff_trusted_falls_back_to_remote_addr(self) -> None:
        """All XFF entries trusted → fall back to REMOTE_ADDR."""
        meta = {
            "REMOTE_ADDR": "10.0.0.1",
            "HTTP_X_FORWARDED_FOR": "10.0.0.5,10.0.0.6",
        }
        assert resolve_client_ip(meta) == "10.0.0.1"

    @override_settings(
        SENDPARCEL_TRUSTED_PROXIES=["10.0.0.0/8", "172.16.0.0/12"]
    )
    def test_multiple_trusted_networks(self) -> None:
        """Multiple trusted CIDRs in TRUSTED_PROXIES."""
        meta = {
            "REMOTE_ADDR": "172.16.0.1",
            "HTTP_X_FORWARDED_FOR": "192.168.1.100,203.0.113.50",
        }
        assert resolve_client_ip(meta) == "203.0.113.50"

    @override_settings(SENDPARCEL_TRUSTED_PROXIES=["10.0.0.0/8"])
    def test_single_xff_entry(self) -> None:
        """Single XFF entry (no intermediate proxies)."""
        meta = {
            "REMOTE_ADDR": "10.0.0.1",
            "HTTP_X_FORWARDED_FOR": "203.0.113.50",
        }
        assert resolve_client_ip(meta) == "203.0.113.50"

    @override_settings(SENDPARCEL_TRUSTED_PROXIES=["10.0.0.0/8"])
    def test_xff_with_whitespace(self) -> None:
        """XFF entries may have leading/trailing whitespace."""
        meta = {
            "REMOTE_ADDR": "10.0.0.1",
            "HTTP_X_FORWARDED_FOR": " 192.168.1.100 , 203.0.113.50 ",
        }
        assert resolve_client_ip(meta) == "203.0.113.50"

    def test_missing_remote_addr(self) -> None:
        """Missing REMOTE_ADDR returns empty string."""
        meta = {}
        assert resolve_client_ip(meta) == ""

    @override_settings(SENDPARCEL_TRUSTED_PROXIES=["invalid-cidr"])
    def test_malformed_cidr_skipped_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Malformed CIDR in SENDPARCEL_TRUSTED_PROXIES is skipped, but
        loudly — a typo silently disabling proxy resolution would
        silently break webhook IP verification."""
        meta = {
            "REMOTE_ADDR": "203.0.113.50",
            "HTTP_X_FORWARDED_FOR": "192.168.1.1",
        }
        with caplog.at_level(logging.WARNING):
            # No trusted networks can be built → REMOTE_ADDR
            assert resolve_client_ip(meta) == "203.0.113.50"

        assert any("invalid-cidr" in r.message for r in caplog.records)

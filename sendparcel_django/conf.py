"""Django settings integration for sendparcel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings


@dataclass(frozen=True)
class SendparcelSettings:
    """Resolved sendparcel configuration from Django settings."""

    PROVIDER_SETTINGS: dict[str, Any]
    DEFAULT_PROVIDER: str
    SHIPMENT_MODEL: str


def get_settings() -> SendparcelSettings:
    """Read sendparcel configuration from Django settings.

    Reads fresh values from ``django.conf.settings`` on every call
    so that ``@override_settings`` in tests works correctly.
    """
    return SendparcelSettings(
        PROVIDER_SETTINGS=getattr(settings, "SENDPARCEL_PROVIDER_SETTINGS", {}),
        DEFAULT_PROVIDER=getattr(settings, "SENDPARCEL_DEFAULT_PROVIDER", ""),
        SHIPMENT_MODEL=getattr(
            settings,
            "SENDPARCEL_SHIPMENT_MODEL",
            "sendparcel_django.Shipment",
        ),
    )

"""Django settings integration for sendparcel."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.conf import settings


@dataclass(frozen=True)
class SendparcelSettings:
    """Resolved sendparcel configuration from Django settings."""

    PROVIDER_SETTINGS: dict[str, Any]
    DEFAULT_PROVIDER: str
    SHIPMENT_MODEL: str
    WEBHOOK_DEDUP_WINDOW: int = 900
    WEBHOOK_MAX_PAYLOAD_SIZE: int = 65536  # 64 KB
    CALLBACK_RETRY_MAX_ATTEMPTS: int = 5
    CALLBACK_RETRY_BACKOFF_BASE: int = 60
    CALLBACK_RETRY_BACKOFF_JITTER: float = 0.1  # 10% jitter
    WEBHOOK_CONTENT_TYPE: str = "application/json"
    TRUSTED_PROXIES: list[str] = field(default_factory=list)


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
            "SENDPARCEL_DJANGO_SHIPMENT_MODEL",
            "sendparcel_django.Shipment",
        ),
        WEBHOOK_DEDUP_WINDOW=getattr(
            settings, "SENDPARCEL_WEBHOOK_DEDUP_WINDOW", 900
        ),
        WEBHOOK_MAX_PAYLOAD_SIZE=getattr(
            settings, "SENDPARCEL_WEBHOOK_MAX_PAYLOAD_SIZE", 65536
        ),
        CALLBACK_RETRY_MAX_ATTEMPTS=getattr(
            settings, "SENDPARCEL_CALLBACK_RETRY_MAX_ATTEMPTS", 5
        ),
        CALLBACK_RETRY_BACKOFF_BASE=getattr(
            settings, "SENDPARCEL_CALLBACK_RETRY_BACKOFF_BASE", 60
        ),
        CALLBACK_RETRY_BACKOFF_JITTER=getattr(
            settings, "SENDPARCEL_CALLBACK_RETRY_BACKOFF_JITTER", 0.1
        ),
        WEBHOOK_CONTENT_TYPE=getattr(
            settings,
            "SENDPARCEL_WEBHOOK_CONTENT_TYPE",
            "application/json",
        ),
        TRUSTED_PROXIES=getattr(
            settings, "SENDPARCEL_TRUSTED_PROXIES", []
        )
        or [],
    )

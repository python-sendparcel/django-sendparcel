"""Abstract model mixins and concrete models for sendparcel."""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

import swapper
from django.core.validators import MinValueValidator
from django.db import models


class ShipmentModelMixin(models.Model):
    """Abstract shipment model contract for sendparcel integrations."""

    provider = models.CharField(max_length=64)
    status = models.CharField(max_length=32, default="new")
    external_id = models.CharField(max_length=128, blank=True, default="")
    tracking_number = models.CharField(max_length=128, blank=True, default="")
    reference_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Reference ID",
        help_text="External reference identifier (e.g. order ID, return ID)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Shipment(ShipmentModelMixin):
    """Default concrete shipment model.

    Swappable via SENDPARCEL_DJANGO_SHIPMENT_MODEL.
    """

    class Meta(ShipmentModelMixin.Meta):
        swappable = swapper.swappable_setting("sendparcel_django", "Shipment")

    def __str__(self) -> str:
        return f"Shipment {self.pk} ({self.provider}: {self.status})"


class CallbackRetry(models.Model):
    """Persists failed callback attempts for retry processing."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shipment_id = models.CharField(max_length=128, db_index=True)
    provider_slug = models.CharField(max_length=64, default="unknown")
    payload = models.JSONField(default=dict)
    headers = models.JSONField(default=dict)
    attempts = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
    )
    next_retry_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=32,
        default="pending",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["created_at"]

    def __str__(self) -> str:
        return f"CallbackRetry({self.shipment_id}, {self.status})"


class WebhookDedup(models.Model):
    """Deduplicates webhook callbacks by payload hash.

    Stores a SHA-256 hash of the webhook payload and the timestamp of
    first receipt.  Old entries are cleaned up by a management command
    or periodic task.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payload_hash = models.CharField(max_length=64, db_index=True)
    shipment_id = models.CharField(max_length=128, db_index=True)
    provider_slug = models.CharField(max_length=64, default="unknown")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["created_at"]
        constraints: ClassVar[list[Any]] = [
            models.UniqueConstraint(
                fields=["shipment_id", "payload_hash"],
                name="%(app_label)s_%(class)s_shipment_hash_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"WebhookDedup({self.payload_hash}, {self.shipment_id})"

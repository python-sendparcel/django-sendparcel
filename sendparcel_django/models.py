"""Abstract model mixins and concrete models for sendparcel."""

from __future__ import annotations

from decimal import Decimal

import swapper
from django.db import models


class OrderModelMixin(models.Model):
    """Abstract order model contract for sendparcel integrations."""

    class Meta:
        abstract = True

    def get_total_weight(self) -> Decimal:
        raise NotImplementedError

    def get_parcels(self) -> list[dict]:
        raise NotImplementedError

    def get_sender_address(self) -> dict:
        raise NotImplementedError

    def get_receiver_address(self) -> dict:
        raise NotImplementedError


class ShipmentModelMixin(models.Model):
    """Abstract shipment model contract for sendparcel integrations."""

    provider = models.CharField(max_length=64)
    status = models.CharField(max_length=32, default="new")
    external_id = models.CharField(max_length=128, blank=True, default="")
    tracking_number = models.CharField(max_length=128, blank=True, default="")
    label_url = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Shipment(ShipmentModelMixin):
    """Default concrete shipment model.

    Swappable via SENDPARCEL_SHIPMENT_MODEL.
    """

    order_id = models.CharField(max_length=255, db_index=True)

    class Meta(ShipmentModelMixin.Meta):
        swappable = swapper.swappable_setting("sendparcel_django", "Shipment")

    def __str__(self) -> str:
        return f"Shipment {self.pk} ({self.provider}: {self.status})"

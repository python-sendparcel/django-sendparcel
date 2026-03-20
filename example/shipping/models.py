"""Concrete Shipment model for the example project."""

from typing import ClassVar

from django.db import models
from sendparcel_django.models import ShipmentModelMixin


class Shipment(ShipmentModelMixin):
    """Concrete shipment for the example project.

    Stores sender/receiver addresses, parcel dimensions, and
    integrates with sendparcel via ShipmentModelMixin.
    """

    # Sender address fields
    sender_name = models.CharField(
        "sender name", max_length=128, default="Example Warehouse"
    )
    sender_street = models.CharField(
        "sender street", max_length=255, default="1 Warehouse St"
    )
    sender_city = models.CharField(
        "sender city", max_length=128, default="Warsaw"
    )
    sender_postal_code = models.CharField(
        "sender postal code", max_length=16, default="00-001"
    )
    sender_country_code = models.CharField(
        "sender country code", max_length=2, default="PL"
    )

    # Receiver address fields
    receiver_name = models.CharField("receiver name", max_length=128)
    receiver_street = models.CharField("receiver street", max_length=255)
    receiver_city = models.CharField("receiver city", max_length=128)
    receiver_postal_code = models.CharField(
        "receiver postal code", max_length=16
    )
    receiver_country_code = models.CharField(
        "receiver country code", max_length=2, default="PL"
    )

    # Parcel dimensions
    weight = models.DecimalField(
        "weight (kg)", max_digits=8, decimal_places=2, default=1
    )
    width = models.PositiveIntegerField("width (cm)", default=10)
    height = models.PositiveIntegerField("height (cm)", default=10)
    length = models.PositiveIntegerField("length (cm)", default=10)

    created_at = models.DateTimeField("created at", auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        verbose_name = "shipment"
        verbose_name_plural = "shipments"

    def __str__(self):
        return f"Shipment #{self.pk} ({self.get_status_display()})"

    def get_status_display(self):
        """Return human-readable status label."""
        status_labels = {
            "new": "New",
            "created": "Created",
            "label_ready": "Label ready",
            "in_transit": "In transit",
            "out_for_delivery": "Out for delivery",
            "delivered": "Delivered",
            "cancelled": "Cancelled",
            "failed": "Failed",
            "returned": "Returned",
        }
        return status_labels.get(self.status, self.status)

    @property
    def status_color(self):
        """Return Tabler color for the status."""
        colors = {
            "new": "secondary",
            "created": "info",
            "label_ready": "cyan",
            "in_transit": "blue",
            "out_for_delivery": "indigo",
            "delivered": "success",
            "cancelled": "warning",
            "failed": "danger",
            "returned": "orange",
        }
        return colors.get(self.status, "secondary")

"""Concrete Order and Shipment models for the example project."""

from decimal import Decimal
from typing import ClassVar

from django.db import models
from sendparcel_django.models import OrderModelMixin, ShipmentModelMixin


class Order(OrderModelMixin):
    """Demo order demonstrating sendparcel integration."""

    PACKAGE_SIZE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("S", "Small (up to 1 kg)"),
        ("M", "Medium (up to 5 kg)"),
        ("L", "Large (up to 15 kg)"),
    ]

    PACKAGE_WEIGHTS: ClassVar[dict[str, Decimal]] = {
        "S": Decimal("0.5"),
        "M": Decimal("2.5"),
        "L": Decimal("10.0"),
    }

    description = models.CharField("description", max_length=255)
    package_size = models.CharField(
        "package size",
        max_length=2,
        choices=PACKAGE_SIZE_CHOICES,
        default="M",
    )

    # Sender (warehouse) fields — fixed for the demo
    sender_name = models.CharField(
        "sender name", max_length=128, default="Example Warehouse"
    )
    sender_line1 = models.CharField(
        "sender address", max_length=255, default="1 Warehouse St"
    )
    sender_city = models.CharField(
        "sender city", max_length=128, default="Warsaw"
    )
    sender_postal_code = models.CharField(
        "sender postal code", max_length=16, default="00-001"
    )

    # Recipient fields
    recipient_name = models.CharField("recipient name", max_length=128)
    recipient_email = models.EmailField("recipient email")
    recipient_phone = models.CharField("recipient phone", max_length=32)
    recipient_line1 = models.CharField("recipient address", max_length=255)
    recipient_city = models.CharField("recipient city", max_length=128)
    recipient_postal_code = models.CharField(
        "recipient postal code", max_length=16
    )

    created_at = models.DateTimeField("created at", auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        verbose_name = "order"
        verbose_name_plural = "orders"

    def __str__(self):
        return f"Order #{self.pk}: {self.description}"

    def get_total_weight(self):
        return self.PACKAGE_WEIGHTS.get(self.package_size, Decimal("2.5"))

    def get_parcels(self):
        return [
            {
                "weight_kg": self.get_total_weight(),
            }
        ]

    def get_sender_address(self):
        return {
            "name": self.sender_name,
            "line1": self.sender_line1,
            "city": self.sender_city,
            "postal_code": self.sender_postal_code,
            "country_code": "PL",
        }

    def get_receiver_address(self):
        return {
            "name": self.recipient_name,
            "line1": self.recipient_line1,
            "city": self.recipient_city,
            "postal_code": self.recipient_postal_code,
            "country_code": "PL",
            "email": self.recipient_email,
            "phone": self.recipient_phone,
        }


class Shipment(ShipmentModelMixin):
    """Concrete shipment for the example project."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="shipments",
        verbose_name="order",
    )
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

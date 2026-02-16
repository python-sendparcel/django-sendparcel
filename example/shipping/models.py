"""Concrete Order and Shipment models for the example project."""

from decimal import Decimal
from typing import ClassVar

from django.db import models
from sendparcel_django.models import OrderModelMixin, ShipmentModelMixin


class Order(OrderModelMixin):
    """Demo order demonstrating sendparcel integration."""

    PACKAGE_SIZE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("S", "Mały (do 1 kg)"),
        ("M", "Średni (do 5 kg)"),
        ("L", "Duży (do 15 kg)"),
    ]

    PACKAGE_WEIGHTS: ClassVar[dict[str, Decimal]] = {
        "S": Decimal("0.5"),
        "M": Decimal("2.5"),
        "L": Decimal("10.0"),
    }

    description = models.CharField("opis", max_length=255)
    package_size = models.CharField(
        "rozmiar paczki",
        max_length=2,
        choices=PACKAGE_SIZE_CHOICES,
        default="M",
    )

    # Sender (warehouse) fields — fixed for the demo
    sender_name = models.CharField(
        "nazwa nadawcy", max_length=128, default="Przykładowy Magazyn"
    )
    sender_line1 = models.CharField(
        "adres nadawcy", max_length=255, default="ul. Magazynowa 1"
    )
    sender_city = models.CharField(
        "miasto nadawcy", max_length=128, default="Warszawa"
    )
    sender_postal_code = models.CharField(
        "kod pocztowy nadawcy", max_length=16, default="00-001"
    )

    # Recipient fields
    recipient_name = models.CharField("nazwa odbiorcy", max_length=128)
    recipient_email = models.EmailField("e-mail odbiorcy")
    recipient_phone = models.CharField("telefon odbiorcy", max_length=32)
    recipient_line1 = models.CharField("adres odbiorcy", max_length=255)
    recipient_city = models.CharField("miasto odbiorcy", max_length=128)
    recipient_postal_code = models.CharField(
        "kod pocztowy odbiorcy", max_length=16
    )

    created_at = models.DateTimeField("utworzono", auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        verbose_name = "zamówienie"
        verbose_name_plural = "zamówienia"

    def __str__(self):
        return f"Zamówienie #{self.pk}: {self.description}"

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
        verbose_name="zamówienie",
    )
    created_at = models.DateTimeField("utworzono", auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        verbose_name = "przesyłka"
        verbose_name_plural = "przesyłki"

    def __str__(self):
        return f"Przesyłka #{self.pk} ({self.get_status_display()})"

    def get_status_display(self):
        """Return Polish status label."""
        status_labels = {
            "new": "Nowa",
            "created": "Utworzona",
            "label_ready": "Etykieta gotowa",
            "in_transit": "W transporcie",
            "out_for_delivery": "W doręczeniu",
            "delivered": "Doręczona",
            "cancelled": "Anulowana",
            "failed": "Błąd",
            "returned": "Zwrócona",
        }
        return status_labels.get(self.status, self.status)

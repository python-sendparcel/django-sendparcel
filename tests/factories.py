"""Model factories for django-sendparcel tests."""

from __future__ import annotations

import factory
from sendparcel.enums import ShipmentStatus

from sendparcel_django.models import Shipment


class ShipmentFactory(factory.django.DjangoModelFactory):
    """Factory for Shipment model instances."""

    class Meta:
        model = Shipment

    provider = "dummy"
    status = ShipmentStatus.NEW
    external_id = ""
    tracking_number = ""
    label_url = ""
    order_id = factory.Sequence(lambda n: f"order-{n}")

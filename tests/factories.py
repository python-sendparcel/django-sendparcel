"""Model factories for django-sendparcel tests."""

from __future__ import annotations

import factory
from sendparcel.enums import ShipmentStatus
from sendparcel_django.models import CallbackRetry, Shipment


class ShipmentFactory(factory.django.DjangoModelFactory):
    """Factory for Shipment model instances."""

    class Meta:
        model = Shipment

    provider = "dummy"
    status = ShipmentStatus.NEW
    external_id = ""
    tracking_number = ""
    label_url = ""
    reference_id = factory.Sequence(lambda n: f"ref-{n}")


class CallbackRetryFactory(factory.django.DjangoModelFactory):
    """Factory for CallbackRetry model instances."""

    class Meta:
        model = CallbackRetry

    shipment_id = factory.Sequence(lambda n: f"ship-{n}")
    payload = factory.LazyFunction(dict)
    headers = factory.LazyFunction(dict)
    status = "pending"
    attempts = 0

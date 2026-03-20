"""Core transition integration tests with Django model instances."""

from __future__ import annotations

from typing import Any, cast

import pytest
from sendparcel.enums import ShipmentStatus
from sendparcel.exceptions import InvalidTransitionError
from sendparcel.fsm import transition_shipment
from sendparcel_django.models import Shipment
from sendparcel_django.protocols import DjangoShipmentAdapter


@pytest.mark.django_db
class TestFSMWithDjangoModel:
    """Verify core transitions work through Django model instances."""

    def test_happy_path_new_to_delivered(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy", reference_id="order-1"
        )

        assert shipment.status == ShipmentStatus.NEW

        transition_shipment(_adapter(shipment), ShipmentStatus.CREATED)
        assert shipment.status == ShipmentStatus.CREATED

        transition_shipment(_adapter(shipment), ShipmentStatus.LABEL_READY)
        assert shipment.status == ShipmentStatus.LABEL_READY

        transition_shipment(_adapter(shipment), ShipmentStatus.IN_TRANSIT)
        assert shipment.status == ShipmentStatus.IN_TRANSIT

        transition_shipment(_adapter(shipment), ShipmentStatus.OUT_FOR_DELIVERY)
        assert shipment.status == ShipmentStatus.OUT_FOR_DELIVERY

        transition_shipment(_adapter(shipment), ShipmentStatus.DELIVERED)
        assert shipment.status == ShipmentStatus.DELIVERED

    def test_cancel_from_new(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy", reference_id="order-2"
        )

        transition_shipment(_adapter(shipment), ShipmentStatus.CANCELLED)
        assert shipment.status == ShipmentStatus.CANCELLED

    def test_cancel_from_created(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            reference_id="order-3",
            status=ShipmentStatus.CREATED,
        )

        transition_shipment(_adapter(shipment), ShipmentStatus.CANCELLED)
        assert shipment.status == ShipmentStatus.CANCELLED

    def test_cancel_from_label_ready(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            reference_id="order-4",
            status=ShipmentStatus.LABEL_READY,
        )

        transition_shipment(_adapter(shipment), ShipmentStatus.CANCELLED)
        assert shipment.status == ShipmentStatus.CANCELLED

    def test_fail_from_new(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy", reference_id="order-5"
        )

        transition_shipment(_adapter(shipment), ShipmentStatus.FAILED)
        assert shipment.status == ShipmentStatus.FAILED

    def test_fail_from_in_transit(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            reference_id="order-6",
            status=ShipmentStatus.IN_TRANSIT,
            tracking_number="TRK-TEST",
        )

        transition_shipment(_adapter(shipment), ShipmentStatus.FAILED)
        assert shipment.status == ShipmentStatus.FAILED

    def test_cannot_deliver_from_new(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy", reference_id="order-7"
        )

        with pytest.raises(InvalidTransitionError):
            transition_shipment(_adapter(shipment), ShipmentStatus.DELIVERED)

    def test_cannot_cancel_from_delivered(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            reference_id="order-8",
            status=ShipmentStatus.DELIVERED,
        )

        with pytest.raises(InvalidTransitionError):
            transition_shipment(_adapter(shipment), ShipmentStatus.CANCELLED)

    def test_mark_in_transit_from_created(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            reference_id="order-9",
            status=ShipmentStatus.CREATED,
        )

        transition_shipment(_adapter(shipment), ShipmentStatus.IN_TRANSIT)
        assert shipment.status == ShipmentStatus.IN_TRANSIT

    def test_mark_returned_from_delivered(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            reference_id="order-10",
            status=ShipmentStatus.DELIVERED,
        )

        transition_shipment(_adapter(shipment), ShipmentStatus.RETURNED)
        assert shipment.status == ShipmentStatus.RETURNED

    def test_same_status_transition_is_allowed(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy", reference_id="order-11"
        )

        transition_shipment(_adapter(shipment), ShipmentStatus.NEW)
        assert shipment.status == ShipmentStatus.NEW

    def test_label_ready_no_longer_requires_label_url(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            reference_id="order-12",
            status=ShipmentStatus.CREATED,
        )

        transition_shipment(_adapter(shipment), ShipmentStatus.LABEL_READY)
        assert shipment.status == ShipmentStatus.LABEL_READY


def _adapter(shipment: Shipment) -> Any:
    return cast(Any, DjangoShipmentAdapter(shipment))

"""FSM integration tests with Django model instances."""

import pytest
from sendparcel.enums import ShipmentStatus
from sendparcel.fsm import create_shipment_machine
from sendparcel_django.models import Shipment
from transitions.core import MachineError


@pytest.mark.django_db
class TestFSMWithDjangoModel:
    """Verify FSM transitions work through Django model instances."""

    def test_happy_path_new_to_delivered(self):
        shipment = Shipment.objects.create(provider="dummy", order_id="order-1")
        create_shipment_machine(shipment)

        assert shipment.status == ShipmentStatus.NEW

        shipment.confirm_created()
        assert shipment.status == ShipmentStatus.CREATED

        shipment.label_url = "https://example.com/label.pdf"
        shipment.confirm_label()
        assert shipment.status == ShipmentStatus.LABEL_READY

        shipment.tracking_number = "TRK-001"
        shipment.mark_in_transit()
        assert shipment.status == ShipmentStatus.IN_TRANSIT

        shipment.mark_out_for_delivery()
        assert shipment.status == ShipmentStatus.OUT_FOR_DELIVERY

        shipment.mark_delivered()
        assert shipment.status == ShipmentStatus.DELIVERED

    def test_cancel_from_new(self):
        shipment = Shipment.objects.create(provider="dummy", order_id="order-2")
        create_shipment_machine(shipment)

        shipment.cancel()
        assert shipment.status == ShipmentStatus.CANCELLED

    def test_cancel_from_created(self):
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-3",
            status=ShipmentStatus.CREATED,
        )
        create_shipment_machine(shipment)

        shipment.cancel()
        assert shipment.status == ShipmentStatus.CANCELLED

    def test_cancel_from_label_ready(self):
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-4",
            status=ShipmentStatus.LABEL_READY,
        )
        create_shipment_machine(shipment)

        shipment.cancel()
        assert shipment.status == ShipmentStatus.CANCELLED

    def test_fail_from_new(self):
        shipment = Shipment.objects.create(provider="dummy", order_id="order-5")
        create_shipment_machine(shipment)

        shipment.fail()
        assert shipment.status == ShipmentStatus.FAILED

    def test_fail_from_in_transit(self):
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-6",
            status=ShipmentStatus.IN_TRANSIT,
            tracking_number="TRK-TEST",
        )
        create_shipment_machine(shipment)

        shipment.fail()
        assert shipment.status == ShipmentStatus.FAILED

    def test_cannot_deliver_from_new(self):
        shipment = Shipment.objects.create(provider="dummy", order_id="order-7")
        create_shipment_machine(shipment)

        with pytest.raises(MachineError):
            shipment.mark_delivered()

    def test_cannot_cancel_from_delivered(self):
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-8",
            status=ShipmentStatus.DELIVERED,
        )
        create_shipment_machine(shipment)

        with pytest.raises(MachineError):
            shipment.cancel()

    def test_mark_in_transit_from_created(self):
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-9",
            status=ShipmentStatus.CREATED,
        )
        create_shipment_machine(shipment)

        shipment.tracking_number = "TRK-002"
        shipment.mark_in_transit()
        assert shipment.status == ShipmentStatus.IN_TRANSIT

    def test_mark_returned_from_delivered(self):
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-10",
            status=ShipmentStatus.DELIVERED,
        )
        create_shipment_machine(shipment)

        shipment.mark_returned()
        assert shipment.status == ShipmentStatus.RETURNED

    def test_may_trigger_returns_false_for_invalid(self):
        shipment = Shipment.objects.create(
            provider="dummy", order_id="order-11"
        )
        create_shipment_machine(shipment)

        assert shipment.may_trigger("mark_delivered") is False

    def test_may_trigger_returns_true_for_valid(self):
        shipment = Shipment.objects.create(
            provider="dummy", order_id="order-12"
        )
        create_shipment_machine(shipment)

        assert shipment.may_trigger("confirm_created") is True

    def test_mark_in_transit_without_tracking_number_raises(self):
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-13",
            status=ShipmentStatus.LABEL_READY,
        )
        create_shipment_machine(shipment)

        with pytest.raises(MachineError):
            shipment.mark_in_transit()

    def test_confirm_label_without_label_url_raises(self):
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-14",
            status=ShipmentStatus.CREATED,
        )
        create_shipment_machine(shipment)

        with pytest.raises(MachineError):
            shipment.confirm_label()

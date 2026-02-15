"""Admin action hook tests."""

from sendparcel.enums import ShipmentStatus
from sendparcel.fsm import create_shipment_machine
from sendparcel_django.admin import build_status_actions


class Shipment:
    def __init__(self, status: str) -> None:
        self.status = status


def test_mark_in_transit_action_changes_status() -> None:
    shipment = Shipment(ShipmentStatus.LABEL_READY)
    create_shipment_machine(shipment)
    actions = build_status_actions()

    actions["mark_in_transit"]([shipment])

    assert shipment.status == ShipmentStatus.IN_TRANSIT


def test_cancel_action_changes_status() -> None:
    shipment = Shipment(ShipmentStatus.CREATED)
    create_shipment_machine(shipment)
    actions = build_status_actions()

    actions["cancel"]([shipment])

    assert shipment.status == ShipmentStatus.CANCELLED

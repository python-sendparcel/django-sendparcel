"""Admin helper hooks for shipment actions."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from sendparcel.fsm import create_shipment_machine


def _transition(shipment, trigger_name: str) -> bool:
    create_shipment_machine(shipment)
    may_trigger = getattr(shipment, "may_trigger", None)
    trigger = getattr(shipment, trigger_name, None)
    if may_trigger is None or trigger is None:
        return False
    if not may_trigger(trigger_name):
        return False
    trigger()
    return True


def build_status_actions() -> dict[str, Callable[[Iterable], int]]:
    """Create reusable bulk actions for shipment status transitions."""

    def mark_in_transit(shipments: Iterable) -> int:
        return sum(_transition(s, "mark_in_transit") for s in shipments)

    def cancel(shipments: Iterable) -> int:
        return sum(_transition(s, "cancel") for s in shipments)

    return {
        "mark_in_transit": mark_in_transit,
        "cancel": cancel,
    }

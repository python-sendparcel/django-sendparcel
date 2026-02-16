"""Admin integration for sendparcel."""

from __future__ import annotations

import contextlib
import warnings
from collections.abc import Callable, Iterable
from typing import ClassVar

import swapper
from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered
from sendparcel.fsm import create_shipment_machine
from transitions.core import MachineError


def _transition(shipment, trigger_name: str) -> bool:
    """Attempt a single FSM transition on a shipment instance.

    Returns True if the transition succeeded, False otherwise.
    Guards (``before`` callbacks) may raise ``MachineError`` even when
    ``may_trigger`` returns True, so we catch that explicitly.
    """
    create_shipment_machine(shipment)
    may_trigger = getattr(shipment, "may_trigger", None)
    trigger = getattr(shipment, trigger_name, None)
    if may_trigger is None or trigger is None:
        return False
    if not may_trigger(trigger_name):
        return False
    try:
        trigger()
    except MachineError:
        return False
    return True


def build_status_actions() -> dict[str, Callable[[Iterable], int]]:
    """Create reusable bulk actions for shipment status transitions.

    .. deprecated::
        Use :class:`ShipmentAdmin` instead which registers all actions
        as proper Django admin actions.
    """
    warnings.warn(
        "build_status_actions() is deprecated. "
        "Use ShipmentAdmin with its built-in actions instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    def mark_in_transit(shipments: Iterable) -> int:
        return sum(_transition(s, "mark_in_transit") for s in shipments)

    def cancel(shipments: Iterable) -> int:
        return sum(_transition(s, "cancel") for s in shipments)

    return {
        "mark_in_transit": mark_in_transit,
        "cancel": cancel,
    }


def _get_shipment_model():
    return swapper.load_model("sendparcel_django", "Shipment")


class ShipmentAdmin(admin.ModelAdmin):
    """Full ModelAdmin for the (swappable) Shipment model."""

    list_display = (
        "id",
        "order_id",
        "status",
        "provider",
        "tracking_number",
        "label_url",
        "created_at",
    )
    list_filter = ("status", "provider")
    search_fields = ("tracking_number", "external_id", "order_id")
    readonly_fields = (
        "external_id",
        "tracking_number",
        "label_url",
        "created_at",
        "updated_at",
    )

    actions: ClassVar[list[str]] = [
        "mark_in_transit",
        "mark_delivered",
        "cancel_shipment",
    ]

    @admin.action(description="Mark selected as in transit")
    def mark_in_transit(self, request, queryset):
        count = 0
        for shipment in queryset:
            if _transition(shipment, "mark_in_transit"):
                shipment.save()
                count += 1
        self.message_user(request, f"{count} shipment(s) marked as in transit.")

    @admin.action(description="Mark selected as delivered")
    def mark_delivered(self, request, queryset):
        count = 0
        for shipment in queryset:
            if _transition(shipment, "mark_delivered"):
                shipment.save()
                count += 1
        self.message_user(request, f"{count} shipment(s) marked as delivered.")

    @admin.action(description="Cancel selected shipments")
    def cancel_shipment(self, request, queryset):
        count = 0
        for shipment in queryset:
            if _transition(shipment, "cancel"):
                shipment.save()
                count += 1
        self.message_user(request, f"{count} shipment(s) cancelled.")


# Register the (possibly swapped) Shipment model with ShipmentAdmin.
with contextlib.suppress(AlreadyRegistered):
    admin.site.register(_get_shipment_model(), ShipmentAdmin)

"""Admin integration for sendparcel."""

from __future__ import annotations

import contextlib
import warnings
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, cast

import swapper
from django.contrib import admin
from django.contrib.admin.exceptions import AlreadyRegistered
from django.db import models
from django.http import HttpRequest
from sendparcel.enums import ShipmentStatus
from sendparcel.exceptions import InvalidTransitionError
from sendparcel.fsm import transition_shipment
from sendparcel.protocols import Shipment as CoreShipment

if TYPE_CHECKING:
    ShipmentAdminBase = admin.ModelAdmin[models.Model]
else:
    ShipmentAdminBase = admin.ModelAdmin


def _transition(shipment: Any, trigger_name: str) -> bool:
    """Attempt a single status transition on a shipment instance."""
    target_statuses = {
        "mark_in_transit": ShipmentStatus.IN_TRANSIT,
        "mark_delivered": ShipmentStatus.DELIVERED,
        "cancel": ShipmentStatus.CANCELLED,
    }
    target_status = target_statuses.get(trigger_name)
    if target_status is None:
        return False
    try:
        transition_shipment(cast(CoreShipment, shipment), target_status)
    except InvalidTransitionError:
        return False
    return True


def build_status_actions() -> dict[str, Callable[[Iterable[Any]], int]]:
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

    def mark_in_transit(shipments: Iterable[Any]) -> int:
        return sum(_transition(s, "mark_in_transit") for s in shipments)

    def cancel(shipments: Iterable[Any]) -> int:
        return sum(_transition(s, "cancel") for s in shipments)

    return {
        "mark_in_transit": mark_in_transit,
        "cancel": cancel,
    }


def _get_shipment_model() -> type[models.Model]:
    return cast(
        type[models.Model],
        swapper.load_model("sendparcel_django", "Shipment"),
    )


class ShipmentAdmin(ShipmentAdminBase):
    """Full ModelAdmin for the (swappable) Shipment model."""

    list_display = (
        "id",
        "reference_id",
        "status",
        "provider",
        "tracking_number",
        "created_at",
    )
    list_filter = ("status", "provider")
    search_fields = ("tracking_number", "external_id", "reference_id")
    readonly_fields = (
        "external_id",
        "tracking_number",
        "created_at",
        "updated_at",
    )

    actions = (
        "mark_in_transit",
        "mark_delivered",
        "cancel_shipment",
    )

    @admin.action(description="Mark selected as in transit")
    def mark_in_transit(
        self,
        request: HttpRequest,
        queryset: models.QuerySet[Any],
    ) -> None:
        count = 0
        for shipment in queryset:
            if _transition(shipment, "mark_in_transit"):
                shipment.save()
                count += 1
        self.message_user(request, f"{count} shipment(s) marked as in transit.")

    @admin.action(description="Mark selected as delivered")
    def mark_delivered(
        self,
        request: HttpRequest,
        queryset: models.QuerySet[Any],
    ) -> None:
        count = 0
        for shipment in queryset:
            if _transition(shipment, "mark_delivered"):
                shipment.save()
                count += 1
        self.message_user(request, f"{count} shipment(s) marked as delivered.")

    @admin.action(description="Cancel selected shipments")
    def cancel_shipment(
        self,
        request: HttpRequest,
        queryset: models.QuerySet[Any],
    ) -> None:
        count = 0
        for shipment in queryset:
            if _transition(shipment, "cancel"):
                shipment.save()
                count += 1
        self.message_user(request, f"{count} shipment(s) cancelled.")


# Register the (possibly swapped) Shipment model with ShipmentAdmin.
with contextlib.suppress(AlreadyRegistered):
    admin.site.register(_get_shipment_model(), ShipmentAdmin)

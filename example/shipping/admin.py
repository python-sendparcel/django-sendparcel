"""Admin configuration for the shipping example app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.contrib.admin.exceptions import AlreadyRegistered

from shipping.models import Shipment

if TYPE_CHECKING:
    ShipmentAdminBase = admin.ModelAdmin[Shipment]
else:
    ShipmentAdminBase = admin.ModelAdmin


class ShipmentAdmin(ShipmentAdminBase):
    list_display = [
        "pk",
        "reference_id",
        "provider",
        "status",
        "tracking_number",
        "receiver_name",
        "receiver_city",
        "created_at",
    ]
    list_filter = ["status", "provider"]
    search_fields = [
        "tracking_number",
        "external_id",
        "reference_id",
        "receiver_name",
    ]


try:
    admin.site.register(Shipment, ShipmentAdmin)
except AlreadyRegistered:
    # The library's sendparcel_django.admin auto-registers the swapped
    # Shipment model. If it was registered first, unregister and
    # re-register with our project-specific admin.
    admin.site.unregister(Shipment)
    admin.site.register(Shipment, ShipmentAdmin)

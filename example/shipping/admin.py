"""Admin configuration for the shipping example app."""

from django.contrib import admin

from shipping.models import Order, Shipment


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "description",
        "package_size",
        "recipient_name",
        "recipient_city",
        "created_at",
    ]
    list_filter = ["package_size", "created_at"]
    search_fields = [
        "description",
        "recipient_name",
        "recipient_email",
    ]


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "order",
        "provider",
        "status",
        "tracking_number",
        "created_at",
    ]
    list_filter = ["status", "provider"]
    search_fields = ["tracking_number", "external_id"]
    raw_id_fields = ["order"]

"""Delivery simulator app configuration."""

from django.apps import AppConfig


class DeliverySimConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "delivery_sim"
    verbose_name = "Delivery simulator"

    def ready(self):
        from sendparcel_django.registry import registry

        from delivery_sim.provider import DeliverySimProvider

        registry.register(DeliverySimProvider)

"""Delivery simulator app configuration."""

from django.apps import AppConfig


class DeliverySimConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "delivery_sim"
    verbose_name = "Symulator dostawy"

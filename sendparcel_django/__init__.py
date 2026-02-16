"""Django adapter for sendparcel."""

default_app_config = "sendparcel_django.apps.SendparcelConfig"

from sendparcel_django.forms import ProviderChoiceForm
from sendparcel_django.protocols import (
    DjangoOrderAdapter,
    DjangoShipmentAdapter,
)
from sendparcel_django.registry import DjangoPluginRegistry, registry

__all__ = [
    "DjangoOrderAdapter",
    "DjangoPluginRegistry",
    "DjangoShipmentAdapter",
    "ProviderChoiceForm",
    "registry",
]

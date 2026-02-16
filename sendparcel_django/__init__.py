"""Django adapter for sendparcel."""

from __future__ import annotations

from typing import TYPE_CHECKING

default_app_config = "sendparcel_django.apps.SendparcelConfig"

if TYPE_CHECKING:
    from sendparcel_django.forms import ProviderChoiceForm
    from sendparcel_django.models import (
        OrderModelMixin,
        Shipment,
        ShipmentModelMixin,
    )
    from sendparcel_django.protocols import (
        DjangoOrderAdapter,
        DjangoShipmentAdapter,
    )
    from sendparcel_django.registry import DjangoPluginRegistry, registry

__all__ = [
    "DjangoOrderAdapter",
    "DjangoPluginRegistry",
    "DjangoShipmentAdapter",
    "OrderModelMixin",
    "ProviderChoiceForm",
    "Shipment",
    "ShipmentModelMixin",
    "registry",
]

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "ProviderChoiceForm": ("sendparcel_django.forms", "ProviderChoiceForm"),
    "OrderModelMixin": ("sendparcel_django.models", "OrderModelMixin"),
    "Shipment": ("sendparcel_django.models", "Shipment"),
    "ShipmentModelMixin": ("sendparcel_django.models", "ShipmentModelMixin"),
    "DjangoOrderAdapter": (
        "sendparcel_django.protocols",
        "DjangoOrderAdapter",
    ),
    "DjangoShipmentAdapter": (
        "sendparcel_django.protocols",
        "DjangoShipmentAdapter",
    ),
    "DjangoPluginRegistry": (
        "sendparcel_django.registry",
        "DjangoPluginRegistry",
    ),
    "registry": ("sendparcel_django.registry", "registry"),
}


def __getattr__(name: str) -> object:
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)

"""Django adapter for sendparcel."""

from __future__ import annotations

from typing import TYPE_CHECKING

__version__ = "0.2.0"

default_app_config = "sendparcel_django.apps.SendparcelConfig"

if TYPE_CHECKING:
    from sendparcel_django.forms import ProviderChoiceForm
    from sendparcel_django.models import (
        Shipment,
        ShipmentModelMixin,
    )
    from sendparcel_django.protocols import DjangoShipmentAdapter
    from sendparcel_django.registry import registry
    from sendparcel_django.repository import DjangoShipmentRepository

__all__ = [
    "DjangoShipmentAdapter",
    "DjangoShipmentRepository",
    "ProviderChoiceForm",
    "Shipment",
    "ShipmentModelMixin",
    "__version__",
    "registry",
]

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "ProviderChoiceForm": ("sendparcel_django.forms", "ProviderChoiceForm"),
    "Shipment": ("sendparcel_django.models", "Shipment"),
    "ShipmentModelMixin": ("sendparcel_django.models", "ShipmentModelMixin"),
    "DjangoShipmentAdapter": (
        "sendparcel_django.protocols",
        "DjangoShipmentAdapter",
    ),
    "DjangoShipmentRepository": (
        "sendparcel_django.repository",
        "DjangoShipmentRepository",
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

"""Django-specific registry wrapper."""

from sendparcel.registry import PluginRegistry


class DjangoPluginRegistry(PluginRegistry):
    """Plugin registry with Django integration.

    URL routing for callbacks is handled by ``sendparcel_django.urls``.
    """


registry = DjangoPluginRegistry()

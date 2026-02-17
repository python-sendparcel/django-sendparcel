"""Registry wrapper tests."""

import pytest
from sendparcel.provider import BaseProvider
from sendparcel.registry import PluginRegistry
from sendparcel_django.registry import DjangoPluginRegistry


class FakeProvider(BaseProvider):
    slug = "fake"
    display_name = "Fake"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {}


class AnotherProvider(BaseProvider):
    slug = "another"
    display_name = "Another"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {}


def test_register_and_get_by_slug():
    reg = DjangoPluginRegistry()
    reg.register(FakeProvider)

    assert reg.get_by_slug("fake") is FakeProvider


def test_get_choices_returns_slug_display_pairs():
    reg = DjangoPluginRegistry()
    reg.register(FakeProvider)
    reg.register(AnotherProvider)

    choices = reg.get_choices()

    assert ("fake", "Fake") in choices
    assert ("another", "Another") in choices


def test_inherits_from_core_plugin_registry():
    assert issubclass(DjangoPluginRegistry, PluginRegistry)


def test_unregister_removes_provider():
    reg = DjangoPluginRegistry()
    reg.register(FakeProvider)
    reg.unregister("fake")

    with pytest.raises(KeyError):
        reg.get_by_slug("fake")

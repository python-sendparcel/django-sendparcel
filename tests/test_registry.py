"""Registry wrapper tests."""

from __future__ import annotations

from typing import Any

import pytest
from sendparcel.exceptions import ProviderNotFoundError
from sendparcel.provider import BaseProvider
from sendparcel.registry import PluginRegistry
from sendparcel.types import AddressInfo, ParcelInfo, ShipmentCreateResult


class FakeProvider(BaseProvider):
    slug = "fake"
    display_name = "Fake"

    async def create_shipment(
        self,
        *,
        sender_address: AddressInfo,
        receiver_address: AddressInfo,
        parcels: list[ParcelInfo],
        **kwargs: Any,
    ) -> ShipmentCreateResult:
        return {"external_id": "fake-1"}


class AnotherProvider(BaseProvider):
    slug = "another"
    display_name = "Another"

    async def create_shipment(
        self,
        *,
        sender_address: AddressInfo,
        receiver_address: AddressInfo,
        parcels: list[ParcelInfo],
        **kwargs: Any,
    ) -> ShipmentCreateResult:
        return {"external_id": "another-1"}


def test_register_and_get_by_slug() -> None:
    reg = PluginRegistry()
    reg.register(FakeProvider)

    assert reg.get_by_slug("fake") is FakeProvider


def test_get_choices_returns_slug_display_pairs() -> None:
    reg = PluginRegistry()
    reg.register(FakeProvider)
    reg.register(AnotherProvider)

    choices = reg.get_choices()

    assert ("fake", "Fake") in choices
    assert ("another", "Another") in choices


def test_unregister_removes_provider() -> None:
    reg = PluginRegistry()
    reg.register(FakeProvider)
    reg.unregister("fake")

    with pytest.raises(ProviderNotFoundError):
        reg.get_by_slug("fake")

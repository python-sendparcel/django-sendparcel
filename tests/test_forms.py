"""Form hook tests."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from sendparcel.provider import BaseProvider
from sendparcel.types import AddressInfo, ParcelInfo, ShipmentCreateResult
from sendparcel_django.forms import ProviderChoiceForm
from sendparcel_django.registry import registry


class FakeProvider(BaseProvider):
    slug = "dummy"
    display_name = "Dummy"

    async def create_shipment(
        self,
        *,
        sender_address: AddressInfo,
        receiver_address: AddressInfo,
        parcels: list[ParcelInfo],
        **kwargs: Any,
    ) -> ShipmentCreateResult:
        return {"external_id": "dummy-1"}


def test_provider_choice_form_populates_choices() -> None:
    registry.register(FakeProvider)

    form = ProviderChoiceForm()
    provider_field = cast(forms.ChoiceField, form.fields["provider"])

    choices = list(cast(Any, provider_field.choices))
    assert ("dummy", "Dummy") in choices

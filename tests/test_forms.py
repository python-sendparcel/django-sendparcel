"""Form hook tests."""

from sendparcel.provider import BaseProvider
from sendparcel_django.forms import ProviderChoiceForm
from sendparcel_django.registry import registry


class FakeProvider(BaseProvider):
    slug = "dummy"
    display_name = "Dummy"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {}


def test_provider_choice_form_populates_choices() -> None:
    registry.register(FakeProvider)

    form = ProviderChoiceForm()

    assert ("dummy", "Dummy") in form.fields["provider"].choices

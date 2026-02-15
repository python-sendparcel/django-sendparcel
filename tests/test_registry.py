"""Registry wrapper tests."""

from sendparcel.provider import BaseProvider
from sendparcel_django.registry import DjangoPluginRegistry


class FakeProvider(BaseProvider):
    slug = "fake"
    display_name = "Fake"

    async def create_shipment(self, **kwargs):
        return {}


def test_callback_paths() -> None:
    reg = DjangoPluginRegistry()
    reg.register(FakeProvider)

    assert "callback/fake/" in reg.get_callback_paths()

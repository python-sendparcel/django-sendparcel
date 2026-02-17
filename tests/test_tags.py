"""Template tag tests."""

from __future__ import annotations

from django.template import Context, Template
from sendparcel.enums import ShipmentStatus
from sendparcel.provider import BaseProvider
from sendparcel_django.registry import registry


class FakeProvider(BaseProvider):
    slug = "fake"
    display_name = "Fake Carrier"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {}


class ShipmentStub:
    """Minimal shipment-like object for template rendering."""

    def __init__(
        self,
        *,
        status: str = ShipmentStatus.NEW,
        tracking_number: str = "",
        label_url: str = "",
    ) -> None:
        self.status = status
        self.tracking_number = tracking_number
        self.label_url = label_url


class TestShipmentStatusBadge:
    def test_renders_badge_with_status_text(self) -> None:
        shipment = ShipmentStub(status=ShipmentStatus.NEW)
        html = _render_tag(
            "{% load sendparcel_tags %}{% shipment_status_badge shipment %}",
            {"shipment": shipment},
        )
        assert "new" in html.lower()
        assert "badge" in html.lower()

    def test_delivered_has_success_color(self) -> None:
        shipment = ShipmentStub(status=ShipmentStatus.DELIVERED)
        html = _render_tag(
            "{% load sendparcel_tags %}{% shipment_status_badge shipment %}",
            {"shipment": shipment},
        )
        assert "bg-success" in html

    def test_failed_has_danger_color(self) -> None:
        shipment = ShipmentStub(status=ShipmentStatus.FAILED)
        html = _render_tag(
            "{% load sendparcel_tags %}{% shipment_status_badge shipment %}",
            {"shipment": shipment},
        )
        assert "bg-danger" in html

    def test_cancelled_has_secondary_color(self) -> None:
        shipment = ShipmentStub(status=ShipmentStatus.CANCELLED)
        html = _render_tag(
            "{% load sendparcel_tags %}{% shipment_status_badge shipment %}",
            {"shipment": shipment},
        )
        assert "bg-secondary" in html

    def test_in_transit_has_primary_color(self) -> None:
        shipment = ShipmentStub(status=ShipmentStatus.IN_TRANSIT)
        html = _render_tag(
            "{% load sendparcel_tags %}{% shipment_status_badge shipment %}",
            {"shipment": shipment},
        )
        assert "bg-primary" in html

    def test_new_has_info_color(self) -> None:
        shipment = ShipmentStub(status=ShipmentStatus.NEW)
        html = _render_tag(
            "{% load sendparcel_tags %}{% shipment_status_badge shipment %}",
            {"shipment": shipment},
        )
        assert "bg-info" in html


class TestProviderChoices:
    def test_renders_option_elements(self) -> None:
        registry.register(FakeProvider)
        html = _render_tag(
            "{% load sendparcel_tags %}{% provider_choices %}",
            {},
        )
        assert "<option" in html
        assert 'value="fake"' in html
        assert "Fake Carrier" in html

    def test_renders_empty_when_no_providers(self) -> None:
        html = _render_tag(
            "{% load sendparcel_tags %}{% provider_choices %}",
            {},
        )
        assert "<option" not in html


class TestTrackingInfo:
    def test_renders_tracking_number(self) -> None:
        shipment = ShipmentStub(tracking_number="TRK-123")
        html = _render_tag(
            "{% load sendparcel_tags %}{% tracking_info shipment %}",
            {"shipment": shipment},
        )
        assert "TRK-123" in html

    def test_renders_label_link_when_url_present(self) -> None:
        shipment = ShipmentStub(
            tracking_number="TRK-456",
            label_url="https://labels.example.com/456.pdf",
        )
        html = _render_tag(
            "{% load sendparcel_tags %}{% tracking_info shipment %}",
            {"shipment": shipment},
        )
        assert "TRK-456" in html
        assert 'href="https://labels.example.com/456.pdf"' in html

    def test_no_link_when_label_url_empty(self) -> None:
        shipment = ShipmentStub(tracking_number="TRK-789", label_url="")
        html = _render_tag(
            "{% load sendparcel_tags %}{% tracking_info shipment %}",
            {"shipment": shipment},
        )
        assert "TRK-789" in html
        assert "href=" not in html

    def test_empty_when_no_tracking_number(self) -> None:
        shipment = ShipmentStub(tracking_number="", label_url="")
        html = _render_tag(
            "{% load sendparcel_tags %}{% tracking_info shipment %}",
            {"shipment": shipment},
        )
        stripped = html.strip()
        assert stripped == ""


def _render_tag(template_str: str, context: dict) -> str:
    template = Template(template_str)
    return template.render(Context(context))

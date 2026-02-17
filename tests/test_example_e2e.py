"""E2E tests: full parcel dispatch flow using DeliverySimProvider.

Exercises the complete lifecycle: order → shipment creation → label
generation → PDF download, all driven through the library's
``ShipmentFlow`` orchestrator and the ``DjangoShipmentRepository``.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from asgiref.sync import sync_to_async
from sendparcel.registry import registry as core_registry
from sendparcel_django.repository import DjangoShipmentRepository

if TYPE_CHECKING:
    from sendparcel.flow import ShipmentFlow

# Make the example apps importable (delivery_sim).
_example_dir = str(Path(__file__).resolve().parent.parent / "example")
if _example_dir not in sys.path:
    sys.path.insert(0, _example_dir)

from delivery_sim.provider import DeliverySimProvider  # noqa: E402
from shipping.models import Order  # noqa: E402

PROVIDER_SLUG = "delivery-sim"

PROVIDER_CONFIG: dict[str, dict] = {
    PROVIDER_SLUG: {
        "api_url": "http://localhost:8000/delivery-sim/",
        "callback_token": "example-sim-token-12345",
    },
}


def _get_build_label_pdf():
    """Import ``_build_label_pdf`` from delivery_sim.views.

    ``delivery_sim.views`` has a top-level import of
    ``shipping.models.Shipment``, which requires the ``shipping``
    Django app in ``INSTALLED_APPS``.  The PDF builder is a pure
    function with no Django dependency, so we inject a lightweight
    stub for ``shipping.models`` to allow the import.
    """
    stub_key = "shipping.models"
    stub_installed = stub_key not in sys.modules
    if stub_installed:
        stub = types.ModuleType(stub_key)
        stub.Shipment = type("Shipment", (), {})  # type: ignore[attr-defined]
        sys.modules[stub_key] = stub

    try:
        mod = importlib.import_module("delivery_sim.views")
        return mod._build_label_pdf
    finally:
        if stub_installed:
            sys.modules.pop(stub_key, None)


# Resolve once at module level — safe because this runs after Django setup.
_build_label_pdf = _get_build_label_pdf()


async def _create_order(**overrides) -> Order:
    """Create a real Order in the database for E2E tests.

    ``create_shipment_from_order()`` passes ``order_id`` through to the
    Django repository, so the referenced Order must exist in the DB to
    satisfy the foreign-key constraint on the example Shipment model.
    """
    defaults = {
        "description": "E2E test order",
        "package_size": "M",
        "recipient_name": "Recipient",
        "recipient_email": "recipient@example.com",
        "recipient_phone": "+48123456789",
        "recipient_line1": "5 Destination St",
        "recipient_city": "Krakow",
        "recipient_postal_code": "30-001",
    }
    defaults.update(overrides)
    return await sync_to_async(Order.objects.create)(**defaults)


def _make_flow(repo: DjangoShipmentRepository) -> ShipmentFlow:
    """Build a ``ShipmentFlow`` wired to the delivery-sim provider."""
    from sendparcel.flow import ShipmentFlow

    return ShipmentFlow(repository=repo, config=PROVIDER_CONFIG)


@pytest.mark.django_db(transaction=True)
class TestFullParcelDispatchFlow:
    """E2E: order → shipment → label URL → PDF verification."""

    async def test_create_shipment_and_verify_label(self) -> None:
        """Create shipment for a real order and verify label URL + PDF."""
        core_registry.register(DeliverySimProvider)

        repo = DjangoShipmentRepository()
        flow = _make_flow(repo)
        order = await _create_order(description="Label verification order")

        # --- Step 1: create shipment (provider returns label inline) ---
        shipment = await flow.create_shipment_from_order(order, PROVIDER_SLUG)

        # Basic shipment assertions.
        assert shipment is not None
        assert shipment.provider == PROVIDER_SLUG

        sid = str(shipment.pk)
        assert shipment.external_id == f"SIM-{sid}"
        assert shipment.tracking_number == f"SIM-TRK-{sid}"

        # DeliverySimProvider returns label in create_shipment, so the
        # flow transitions directly to label_ready.
        assert shipment.status == "label_ready"

        # --- Step 2: verify label URL format ---
        assert shipment.label_url, "label_url must be set"
        assert "/delivery-sim/label/" in shipment.label_url
        assert shipment.label_url.endswith(f"{sid}.pdf")

        # --- Step 3: generate PDF and verify content ---
        #
        # This replicates what the label_pdf view does: it builds the
        # label text from the shipment_id extracted from the URL and
        # passes it to _build_label_pdf.
        label_text = f"Shipment label {sid}"
        pdf_bytes = _build_label_pdf(label_text)

        assert pdf_bytes.startswith(b"%PDF-1.4"), (
            "PDF must start with a valid header"
        )
        assert b"%%EOF" in pdf_bytes
        assert len(pdf_bytes) > 100

    async def test_shipment_persisted_in_database(self) -> None:
        """Verify the shipment is retrievable from the database."""
        core_registry.register(DeliverySimProvider)

        repo = DjangoShipmentRepository()
        flow = _make_flow(repo)
        order = await _create_order(description="Persistence test order")

        shipment = await flow.create_shipment_from_order(order, PROVIDER_SLUG)

        retrieved = await repo.get_by_id(str(shipment.pk))
        assert retrieved is not None
        assert retrieved.provider == PROVIDER_SLUG
        assert retrieved.external_id == shipment.external_id
        assert retrieved.tracking_number == shipment.tracking_number
        assert retrieved.label_url == shipment.label_url
        assert retrieved.status == "label_ready"

    async def test_label_pdf_content_structure(self) -> None:
        """Verify the generated PDF has correct internal structure."""
        pdf_bytes = _build_label_pdf("Test Label Content")

        assert pdf_bytes.startswith(b"%PDF-1.4")
        assert b"%%EOF" in pdf_bytes
        assert b"/Type /Catalog" in pdf_bytes
        assert b"/Type /Page" in pdf_bytes
        assert b"/BaseFont /Helvetica" in pdf_bytes
        assert b"Test Label Content" in pdf_bytes

    async def test_label_pdf_escapes_special_characters(self) -> None:
        """Verify parentheses in label text are PDF-escaped."""
        pdf_bytes = _build_label_pdf("Label (special) chars \\here")

        assert pdf_bytes.startswith(b"%PDF-1.4")
        # The text must be present in escaped form.
        assert b"Label \\(special\\) chars \\\\here" in pdf_bytes

    async def test_create_shipment_sets_order_id(self) -> None:
        """Verify the persisted shipment has the correct order_id."""
        core_registry.register(DeliverySimProvider)

        repo = DjangoShipmentRepository()
        flow = _make_flow(repo)
        order = await _create_order(description="Order ID test order")

        shipment = await flow.create_shipment_from_order(order, PROVIDER_SLUG)

        assert shipment.order_id == str(order.pk)


@pytest.mark.django_db(transaction=True)
class TestDummyProviderWithSeparateLabelCreation:
    """E2E: verify create_shipment + create_label path (DummyProvider)."""

    async def test_dummy_provider_needs_separate_create_label(self) -> None:
        """DummyProvider.create_shipment does not return label inline.

        The view must call create_label() separately to get label_url.
        """
        from sendparcel.flow import ShipmentFlow
        from sendparcel.providers.dummy import DummyProvider

        core_registry.register(DummyProvider)

        dummy_config: dict[str, dict] = {
            "dummy": {
                "label_base_url": "https://dummy.local/labels",
            },
        }
        repo = DjangoShipmentRepository()
        flow = ShipmentFlow(repository=repo, config=dummy_config)
        order = await _create_order(description="Dummy provider test order")

        shipment = await flow.create_shipment_from_order(order, "dummy")

        # DummyProvider does NOT return label in create_shipment
        assert shipment.status == "created"
        assert shipment.label_url == ""

        # Separate create_label call
        shipment = await flow.create_label(shipment)

        assert shipment.status == "label_ready"
        assert shipment.label_url, "label_url must be set after create_label"
        assert "dummy.local/labels" in shipment.label_url

        # Verify persisted
        retrieved = await repo.get_by_id(str(shipment.pk))
        assert retrieved.label_url == shipment.label_url
        assert retrieved.status == "label_ready"

    async def test_inline_label_skips_separate_create_label(self) -> None:
        """DeliverySimProvider returns label inline — no extra call needed."""
        core_registry.register(DeliverySimProvider)

        repo = DjangoShipmentRepository()
        flow = _make_flow(repo)
        order = await _create_order(description="Inline label test order")

        shipment = await flow.create_shipment_from_order(order, PROVIDER_SLUG)

        # DeliverySimProvider returns label inline
        assert shipment.status == "label_ready"
        assert shipment.label_url, "label_url set inline by provider"

"""E2E tests: full parcel dispatch flow using DeliverySimProvider.

Exercises the complete lifecycle: shipment creation → label
generation → PDF download, all driven through the library's
``ShipmentFlow`` orchestrator and the ``DjangoShipmentRepository``.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest
from sendparcel.registry import registry as core_registry
from sendparcel_django.repository import DjangoShipmentRepository

# Make the example apps importable (delivery_sim).
_example_dir = str(Path(__file__).resolve().parent.parent / "example")
if _example_dir not in sys.path:
    sys.path.insert(0, _example_dir)

from delivery_sim.provider import DeliverySimProvider  # noqa: E402

PROVIDER_SLUG = "delivery-sim"

PROVIDER_CONFIG: dict[str, dict] = {
    PROVIDER_SLUG: {
        "api_url": "http://localhost:8000/delivery-sim/",
        "callback_token": "example-sim-token-12345",
    },
}

SENDER_ADDRESS = {
    "name": "Test Warehouse",
    "line1": "1 Warehouse St",
    "city": "Warsaw",
    "postal_code": "00-001",
    "country_code": "PL",
}

RECEIVER_ADDRESS = {
    "name": "Recipient",
    "line1": "5 Destination St",
    "city": "Krakow",
    "postal_code": "30-001",
    "country_code": "PL",
}

PARCELS = [{"weight_kg": 2.5}]


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


def _make_flow(repo: DjangoShipmentRepository):
    """Build a ``ShipmentFlow`` wired to the delivery-sim provider."""
    from sendparcel.flow import ShipmentFlow

    return ShipmentFlow(repository=repo, config=PROVIDER_CONFIG)


@pytest.mark.django_db(transaction=True)
class TestFullParcelDispatchFlow:
    """E2E: shipment creation → label URL → PDF verification."""

    async def test_create_shipment_and_verify_label(self) -> None:
        """Create shipment and verify label URL + PDF."""
        core_registry.register(DeliverySimProvider)

        repo = DjangoShipmentRepository()
        flow = _make_flow(repo)

        # --- Step 1: create shipment (provider returns label inline) ---
        shipment = await flow.create_shipment(
            PROVIDER_SLUG,
            sender_address=SENDER_ADDRESS,
            receiver_address=RECEIVER_ADDRESS,
            parcels=PARCELS,
            reference_id="label-verification-ref",
        )

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

        shipment = await flow.create_shipment(
            PROVIDER_SLUG,
            sender_address=SENDER_ADDRESS,
            receiver_address=RECEIVER_ADDRESS,
            parcels=PARCELS,
            reference_id="persistence-test-ref",
        )

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

    async def test_create_shipment_sets_reference_id(self) -> None:
        """Verify the persisted shipment has the correct reference_id."""
        core_registry.register(DeliverySimProvider)

        repo = DjangoShipmentRepository()
        flow = _make_flow(repo)

        shipment = await flow.create_shipment(
            PROVIDER_SLUG,
            sender_address=SENDER_ADDRESS,
            receiver_address=RECEIVER_ADDRESS,
            parcels=PARCELS,
            reference_id="ref-id-test-123",
        )

        assert shipment.reference_id == "ref-id-test-123"


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

        shipment = await flow.create_shipment(
            "dummy",
            sender_address=SENDER_ADDRESS,
            receiver_address=RECEIVER_ADDRESS,
            parcels=PARCELS,
            reference_id="dummy-provider-test-ref",
        )

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

        shipment = await flow.create_shipment(
            PROVIDER_SLUG,
            sender_address=SENDER_ADDRESS,
            receiver_address=RECEIVER_ADDRESS,
            parcels=PARCELS,
            reference_id="inline-label-test-ref",
        )

        # DeliverySimProvider returns label inline
        assert shipment.status == "label_ready"
        assert shipment.label_url, "label_url set inline by provider"

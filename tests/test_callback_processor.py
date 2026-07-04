"""Tests for CallbackProcessor."""

from __future__ import annotations

import json
from typing import Any, ClassVar, cast

import pytest
from sendparcel.enums import ShipmentStatus
from sendparcel.exceptions import (
    CommunicationError,
)
from sendparcel.protocols import ShipmentRepository
from sendparcel.provider import BaseProvider
from sendparcel.types import (
    AddressInfo,
    CallbackContext,
    ParcelInfo,
    ShipmentCreateResult,
    ShipmentUpdateResult,
)
from sendparcel_django.callback import CallbackProcessor, DuplicateCallbackError
from sendparcel_django.registry import registry as django_registry


class DummyShipment:
    id = 1
    status = ShipmentStatus.LABEL_READY
    provider = "dummy"
    external_id = ""
    tracking_number = "TRK-TEST"

    def save(self) -> None:
        pass


class DummyProvider(BaseProvider):
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
        return {"external_id": "ext-1"}

    async def verify_callback(
        self,
        ctx: CallbackContext,
        **kwargs: Any,
    ) -> None:
        pass

    async def handle_callback(
        self,
        ctx: CallbackContext,
        **kwargs: Any,
    ) -> ShipmentUpdateResult:
        return {"status": ShipmentStatus.IN_TRANSIT}


class DummyRepository:
    def __init__(self) -> None:
        self.shipment = DummyShipment()

    def get_by_id_sync(
        self, shipment_id: str, *, for_update: bool = False
    ) -> DummyShipment:
        return self.shipment

    async def get_by_id(
        self, shipment_id: str, *, for_update: bool = False
    ) -> DummyShipment:
        return self.shipment

    async def create(self, **kwargs: Any) -> DummyShipment:
        raise NotImplementedError

    async def save(self, shipment: DummyShipment) -> DummyShipment:
        self.shipment = shipment
        return shipment

    async def update_status(
        self, shipment_id: str, status: str, **fields: Any
    ) -> DummyShipment:
        raise NotImplementedError

    async def update_fields(
        self, shipment_id: str, **fields: Any
    ) -> DummyShipment:
        """Atomic field update (simulates DB-level atomicity)."""
        for key, value in fields.items():
            setattr(self.shipment, key, value)
        return self.shipment

    async def delete(self, shipment_id: str) -> None:
        pass

    async def find_by_reference(
        self, provider: str, reference_id: str
    ) -> DummyShipment | None:
        return self.shipment if self.shipment.provider == provider else None

    async def create_with_idempotency_key(
        self,
        provider: str,
        status: str,
        reference_id: str,
        **kwargs: Any,
    ) -> tuple[DummyShipment | None, DummyShipment | None]:
        """Atomically check for existing + create if absent."""
        if (
            self.shipment.provider == provider
            and str(self.shipment.id) == reference_id
        ):
            return (self.shipment, None)
        new = DummyShipment()
        new.id = int(reference_id) if reference_id.isdigit() else 0
        new.provider = provider
        new.status = status  # type: ignore[assignment]
        self.shipment = new
        return (None, new)


class CommunicationErrorProvider(BaseProvider):
    slug = "comm_err"
    display_name = "CommErr"

    async def create_shipment(
        self,
        *,
        sender_address: AddressInfo,
        receiver_address: AddressInfo,
        parcels: list[ParcelInfo],
        **kwargs: Any,
    ) -> ShipmentCreateResult:
        return {"external_id": "ext-1"}

    async def verify_callback(
        self,
        ctx: CallbackContext,
        **kwargs: Any,
    ) -> None:
        raise CommunicationError("Provider API unreachable")

    async def handle_callback(
        self,
        ctx: CallbackContext,
        **kwargs: Any,
    ) -> ShipmentUpdateResult:
        return {}


class MockDedupStore:
    """Test double for DjangoWebhookDedupStore."""

    def __init__(self, is_dup: bool = False) -> None:
        self.is_dup = is_dup
        self.released: list[CallbackContext] = []

    async def is_duplicate(self, ctx: CallbackContext) -> bool:
        return self.is_dup

    async def release(self, ctx: CallbackContext) -> None:
        self.released.append(ctx)


@pytest.mark.django_db(transaction=True)
async def test_processor_process_success() -> None:
    """process(ctx) returns outcome when dedup and provider succeed."""
    django_registry.register(DummyProvider)
    repository = cast(ShipmentRepository, DummyRepository())
    processor = CallbackProcessor(repository)

    # Patch dedup to return False (not a duplicate)
    import sendparcel_django.callback as callback_module

    original_store = callback_module.DjangoWebhookDedupStore
    callback_module.DjangoWebhookDedupStore = lambda: MockDedupStore(
        is_dup=False
    )

    try:
        ctx = CallbackContext(
            shipment_id="1",
            payload={"event": "picked_up"},
            headers={},
            source_ip="127.0.0.1",
            raw_body=b'{"event": "picked_up"}',
        )

        outcome = await processor.process(ctx)

        assert outcome.shipment.status == ShipmentStatus.IN_TRANSIT
        assert outcome.update["status"] == ShipmentStatus.IN_TRANSIT
    finally:
        callback_module.DjangoWebhookDedupStore = original_store


@pytest.mark.django_db(transaction=True)
async def test_processor_dedup_skips_duplicate() -> None:
    """processor returns early when dedup_hash already seen."""
    django_registry.register(DummyProvider)
    repository = cast(ShipmentRepository, DummyRepository())
    processor = CallbackProcessor(repository)

    # Patch dedup to return True (duplicate detected)
    import sendparcel_django.callback as callback_module

    original_store = callback_module.DjangoWebhookDedupStore
    callback_module.DjangoWebhookDedupStore = lambda: MockDedupStore(
        is_dup=True
    )

    try:
        ctx = CallbackContext(
            shipment_id="1",
            payload={"event": "picked_up"},
            headers={},
            source_ip="127.0.0.1",
            raw_body=b'{"event": "picked_up"}',
        )

        with pytest.raises(DuplicateCallbackError) as exc_info:
            await processor.process(ctx)

        assert exc_info.value.shipment_id == "1"
        assert "Duplicate callback for shipment 1" in str(exc_info.value)
    finally:
        callback_module.DjangoWebhookDedupStore = original_store


@pytest.mark.django_db(transaction=True)
async def test_processor_stores_retry_on_communication_error() -> None:
    """processor stores callback for retry on CommunicationError."""
    django_registry.register(CommunicationErrorProvider)

    # Set up shipment with communication error provider
    repository = cast(ShipmentRepository, DummyRepository())
    repository.shipment.provider = "comm_err"

    processor = CallbackProcessor(repository)

    # Patch dedup to return False (not a duplicate)
    import sendparcel_django.callback as callback_module

    original_store = callback_module.DjangoWebhookDedupStore
    callback_module.DjangoWebhookDedupStore = lambda: MockDedupStore(
        is_dup=False
    )

    try:
        ctx = CallbackContext(
            shipment_id="1",
            payload={"event": "status_update"},
            headers={},
            source_ip="127.0.0.1",
            raw_body=b'{"event": "status_update"}',
        )

        # CommunicationError should propagate
        with pytest.raises(CommunicationError) as exc_info:
            await processor.process(ctx)

        assert "Provider API unreachable" in str(exc_info.value)

    finally:
        callback_module.DjangoWebhookDedupStore = original_store


@pytest.mark.django_db(transaction=True)
async def test_failed_processing_releases_dedup_claim() -> None:
    """A failed callback must not poison dedup: when processing raises,
    the provider's redelivery of the identical payload has to be
    processed again, not swallowed as a duplicate."""
    django_registry.register(CommunicationErrorProvider)
    repository = cast(ShipmentRepository, DummyRepository())
    repository.shipment.provider = "comm_err"  # type: ignore[attr-defined]
    processor = CallbackProcessor(repository)

    ctx = CallbackContext(
        shipment_id="1",
        payload={"event": "status_update"},
        headers={},
        source_ip="127.0.0.1",
        raw_body=b'{"event": "status_update"}',
    )

    with pytest.raises(CommunicationError):
        await processor.process(ctx)

    # Redelivery: must hit the provider again (raising CommunicationError),
    # not be short-circuited by DuplicateCallbackError.
    with pytest.raises(CommunicationError):
        await processor.process(ctx)


@pytest.mark.django_db(transaction=True)
async def test_successful_processing_keeps_dedup_claim() -> None:
    """After a successful callback, the identical payload is a duplicate."""
    django_registry.register(DummyProvider)
    repository = cast(ShipmentRepository, DummyRepository())
    processor = CallbackProcessor(repository)

    ctx = CallbackContext(
        shipment_id="1",
        payload={"event": "picked_up"},
        headers={},
        source_ip="127.0.0.1",
        raw_body=b'{"event": "picked_up"}',
    )

    outcome = await processor.process(ctx)
    assert outcome.shipment.status == ShipmentStatus.IN_TRANSIT

    with pytest.raises(DuplicateCallbackError):
        await processor.process(ctx)


class AtomicProbeProvider(BaseProvider):
    """Records whether the callback runs inside a DB transaction."""

    slug = "atomic_probe"
    display_name = "Atomic Probe"
    seen_atomic: ClassVar[list[bool]] = []

    async def create_shipment(
        self,
        *,
        sender_address: AddressInfo,
        receiver_address: AddressInfo,
        parcels: list[ParcelInfo],
        **kwargs: Any,
    ) -> ShipmentCreateResult:
        return {"external_id": "ext-1"}

    async def verify_callback(
        self,
        ctx: CallbackContext,
        **kwargs: Any,
    ) -> None:
        pass

    async def handle_callback(
        self,
        ctx: CallbackContext,
        **kwargs: Any,
    ) -> ShipmentUpdateResult:
        from asgiref.sync import sync_to_async
        from django.db import connection

        in_atomic = await sync_to_async(
            lambda: connection.in_atomic_block,
            thread_sensitive=True,
        )()
        type(self).seen_atomic.append(in_atomic)
        return {"status": ShipmentStatus.IN_TRANSIT}


@pytest.mark.django_db(transaction=True)
async def test_callback_processed_inside_single_locked_transaction() -> None:
    """The whole callback pipeline (load with select_for_update →
    provider → persist) must run inside ONE transaction, so the row
    lock actually serializes concurrent callbacks. Previously the lock
    was released before the provider call and the write."""
    from asgiref.sync import sync_to_async
    from sendparcel_django.models import Shipment
    from sendparcel_django.repository import DjangoShipmentRepository

    AtomicProbeProvider.seen_atomic.clear()
    django_registry.register(AtomicProbeProvider)

    shipment = await sync_to_async(Shipment.objects.create)(
        provider="atomic_probe",
        status=str(ShipmentStatus.LABEL_READY),
    )
    processor = CallbackProcessor(
        cast(ShipmentRepository, DjangoShipmentRepository())
    )
    ctx = CallbackContext(
        shipment_id=str(shipment.pk),
        payload={"event": "picked_up"},
        headers={},
        source_ip="127.0.0.1",
        raw_body=b'{"event": "picked_up"}',
    )

    outcome = await processor.process(ctx)

    assert AtomicProbeProvider.seen_atomic == [True]
    assert str(outcome.shipment.status) == str(ShipmentStatus.IN_TRANSIT)
    fresh = await sync_to_async(Shipment.objects.get)(pk=shipment.pk)
    assert str(fresh.status) == str(ShipmentStatus.IN_TRANSIT)


# Test for view layer error handling


class RequestStub:
    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        *,
        remote_addr: str = "127.0.0.1",
        content_type: str = "application/json",
        body: bytes | None = None,
    ) -> None:
        if body is not None:
            self.body = body
        elif payload is not None:
            self.body = json.dumps(payload).encode("utf-8")
        else:
            self.body = b"{}"
        self.headers = headers or {}
        self.method = "POST"
        self.content_type = content_type
        self.META: dict[str, Any] = {"REMOTE_ADDR": remote_addr}


@pytest.mark.django_db(transaction=True)
async def test_processor_returns_400_on_invalid_json() -> None:
    """view returns 400 for invalid JSON."""
    from sendparcel_django.views import callback

    django_registry.register(DummyProvider)
    repository = cast(ShipmentRepository, DummyRepository())

    # Invalid JSON request
    request = RequestStub(body=b"invalid-json{{{")

    response = await callback(
        cast(Any, request),
        "1",
        repository=repository,
        config={},
    )

    assert response.status_code == 400
    data = json.loads(response.content)
    assert "Invalid JSON" in data["detail"]
    assert data["code"] == "invalid_json"


@pytest.mark.django_db(transaction=True)
async def test_processor_returns_415_on_wrong_content_type() -> None:
    """view returns 415 for wrong content-type."""
    from sendparcel_django.views import callback

    django_registry.register(DummyProvider)
    repository = cast(ShipmentRepository, DummyRepository())

    # Wrong content-type request
    request = RequestStub(
        payload={"event": "picked_up"},
        content_type="text/plain",
    )

    response = await callback(
        cast(Any, request),
        "1",
        repository=repository,
        config={},
    )

    assert response.status_code == 415
    data = json.loads(response.content)
    assert "Content-Type must be application/json" in data["detail"]

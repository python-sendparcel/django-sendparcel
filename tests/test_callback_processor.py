"""Tests for CallbackProcessor."""

from __future__ import annotations

import json
from typing import Any, ClassVar, cast

import pytest
from sendparcel.enums import ShipmentStatus
from sendparcel.exceptions import (
    CommunicationError,
    SendParcelException,
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
    
    async def is_duplicate(self, ctx: CallbackContext) -> bool:
        return self.is_dup


@pytest.mark.django_db(transaction=True)
async def test_processor_process_success() -> None:
    """processor.process(ctx) returns outcome when dedup passes and provider succeeds."""
    django_registry.register(DummyProvider)
    repository = cast(ShipmentRepository, DummyRepository())
    processor = CallbackProcessor(repository)
    
    # Patch dedup to return False (not a duplicate)
    original_dedup = processor.__class__.__module__
    import sendparcel_django.callback as callback_module
    original_store = callback_module.DjangoWebhookDedupStore
    callback_module.DjangoWebhookDedupStore = lambda: MockDedupStore(is_dup=False)
    
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
    callback_module.DjangoWebhookDedupStore = lambda: MockDedupStore(is_dup=True)
    
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
    callback_module.DjangoWebhookDedupStore = lambda: MockDedupStore(is_dup=False)
    
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
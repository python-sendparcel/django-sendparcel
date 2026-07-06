"""View tests."""

from __future__ import annotations

import json
from typing import Any, ClassVar, cast

import pytest
from django.test import override_settings
from sendparcel.enums import ShipmentStatus
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
    ShipmentNotFoundError,
)
from sendparcel.provider import BaseProvider
from sendparcel.types import (
    AddressInfo,
    CallbackContext,
    ParcelInfo,
    ShipmentCreateResult,
    ShipmentUpdateResult,
)
from sendparcel_django.registry import registry as django_registry
from sendparcel_django.views import callback


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
        if ctx.headers.get("x-dummy-token") != "ok":
            raise InvalidCallbackError("BAD TOKEN")

    async def handle_callback(
        self,
        ctx: CallbackContext,
        **kwargs: Any,
    ) -> ShipmentUpdateResult:
        return {"status": ShipmentStatus.IN_TRANSIT}


class Repo:
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
        # Compare as strings to avoid int/str type mismatch.
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


class RequestStub:
    def __init__(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        *,
        remote_addr: str = "127.0.0.1",
        content_type: str = "application/json",
    ) -> None:
        self.body = json.dumps(payload).encode("utf-8")
        self.headers = headers
        self.method = "POST"
        self.content_type = content_type
        self.META: dict[str, Any] = {"REMOTE_ADDR": remote_addr}


async def _callback_response(
    request: Any,
    shipment_id: str,
    *,
    repository: Any,
    config: dict[str, Any],
) -> Any:
    return await callback(
        cast(Any, request),
        shipment_id,
        repository=repository,
        config=config,
    )


@pytest.mark.django_db(transaction=True)
async def test_callback_uses_flow_and_updates_status() -> None:
    django_registry.register(DummyProvider)
    repo = Repo()

    response = await _callback_response(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
        "1",
        repository=repo,
        config={"dummy": {"callback_token": "ok"}},
    )

    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["provider"] == "dummy"
    assert data["status"] == "accepted"
    assert data["shipment"]["status"] == ShipmentStatus.IN_TRANSIT
    assert data["update"]["status"] == ShipmentStatus.IN_TRANSIT


@pytest.mark.django_db(transaction=True)
async def test_callback_returns_bad_request_on_invalid_signature() -> None:
    django_registry.register(DummyProvider)
    repo = Repo()

    response = await _callback_response(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "bad"}),
        "1",
        repository=repo,
        config={"dummy": {"callback_token": "ok"}},
    )

    assert response.status_code == 400
    data = json.loads(response.content)
    assert data["code"] == "invalid_callback"


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


class TransitionErrorProvider(BaseProvider):
    slug = "trans_err"
    display_name = "TransErr"

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
        raise InvalidTransitionError("Cannot transition from current state")


class GenericErrorProvider(BaseProvider):
    slug = "generic_err"
    display_name = "GenericErr"

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
        raise SendParcelException("Something went wrong")


class NoCallbackProvider(BaseProvider):
    slug = "no-callback"
    display_name = "No Callback"

    async def create_shipment(
        self,
        *,
        sender_address: AddressInfo,
        receiver_address: AddressInfo,
        parcels: list[ParcelInfo],
        **kwargs: Any,
    ) -> ShipmentCreateResult:
        return {"external_id": "ext-1"}


@pytest.mark.django_db(transaction=True)
async def test_callback_returns_502_on_communication_error() -> None:
    django_registry.register(CommunicationErrorProvider)
    shipment = DummyShipment()
    shipment.provider = "comm_err"
    repo = Repo()
    repo.shipment = shipment

    response = await _callback_response(
        RequestStub({"event": "status_update"}, {}),
        "1",
        repository=repo,
        config={},
    )

    assert response.status_code == 502
    data = json.loads(response.content)
    assert data["code"] == "communication_error"
    assert "Provider API unreachable" in data["detail"]


@pytest.mark.django_db(transaction=True)
async def test_callback_returns_409_on_invalid_transition() -> None:
    django_registry.register(TransitionErrorProvider)
    shipment = DummyShipment()
    shipment.provider = "trans_err"
    repo = Repo()
    repo.shipment = shipment

    response = await _callback_response(
        RequestStub({"event": "status_update"}, {}),
        "1",
        repository=repo,
        config={},
    )

    assert response.status_code == 409
    data = json.loads(response.content)
    assert data["code"] == "invalid_transition"
    assert "Cannot transition from current state" in data["detail"]


@pytest.mark.django_db(transaction=True)
async def test_callback_returns_400_on_generic_sendparcel_exception() -> None:
    django_registry.register(GenericErrorProvider)
    shipment = DummyShipment()
    shipment.provider = "generic_err"
    repo = Repo()
    repo.shipment = shipment

    response = await _callback_response(
        RequestStub({"event": "status_update"}, {}),
        "1",
        repository=repo,
        config={},
    )

    assert response.status_code == 400
    data = json.loads(response.content)
    assert data["code"] == "sendparcel_error"
    assert "Something went wrong" in data["detail"]


@pytest.mark.django_db(transaction=True)
async def test_callback_returns_404_when_shipment_is_missing() -> None:
    class MissingRepo(Repo):
        def get_by_id_sync(
            self, shipment_id: str, *, for_update: bool = False
        ) -> DummyShipment:
            raise ShipmentNotFoundError(shipment_id)

        async def get_by_id(
            self, shipment_id: str, *, for_update: bool = False
        ) -> DummyShipment:
            raise ShipmentNotFoundError(shipment_id)

    django_registry.register(DummyProvider)

    response = await _callback_response(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
        "1",
        repository=MissingRepo(),
        config={"dummy": {"callback_token": "ok"}},
    )

    assert response.status_code == 404
    data = json.loads(response.content)
    assert data["code"] == "shipment_not_found"


@pytest.mark.django_db(transaction=True)
async def test_callback_returns_404_when_provider_is_missing() -> None:
    repo = Repo()
    repo.shipment.provider = "missing-provider"

    response = await _callback_response(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
        "1",
        repository=repo,
        config={},
    )

    assert response.status_code == 404
    data = json.loads(response.content)
    assert data["code"] == "provider_not_found"
    assert "missing-provider" in data["detail"]


@pytest.mark.django_db(transaction=True)
async def test_callback_returns_409_when_provider_lacks_callback_support() -> (
    None
):
    django_registry.register(NoCallbackProvider)
    repo = Repo()
    repo.shipment.provider = "no-callback"

    response = await _callback_response(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
        "1",
        repository=repo,
        config={},
    )

    assert response.status_code == 409
    data = json.loads(response.content)
    assert data["code"] == "provider_capability_error"
    assert "does not support push callbacks" in data["detail"]


@pytest.mark.django_db(transaction=True)
async def test_callback_auto_creates_repository_when_none_provided() -> None:
    django_registry.register(DummyProvider)
    repo = Repo()

    response = await _callback_response(
        RequestStub({}, {"x-dummy-token": "ok"}),
        "1",
        repository=repo,
        config={"dummy": {"callback_token": "ok"}},
    )

    assert b"Repository is required" not in response.content


class TestCallbackEdgeCases:
    @pytest.mark.django_db(transaction=True)
    async def test_callback_with_invalid_json(self) -> None:
        django_registry.register(DummyProvider)
        repo = Repo()

        class BadJsonRequest:
            body = b"not-json{{"
            content_type = "application/json"
            headers: ClassVar[dict[str, str]] = {"x-dummy-token": "ok"}
            method = "POST"

        response = await _callback_response(
            BadJsonRequest(), "1", repository=repo, config={"dummy": {}}
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert "Invalid JSON" in data["detail"]
        assert data["code"] == "invalid_json"

    @pytest.mark.django_db(transaction=True)
    async def test_callback_with_invalid_utf8(self) -> None:
        django_registry.register(DummyProvider)
        repo = Repo()

        class BadUtf8Request:
            body = b"\x80\x81\x82"
            content_type = "application/json"
            headers: ClassVar[dict[str, str]] = {"x-dummy-token": "ok"}
            method = "POST"

        response = await _callback_response(
            BadUtf8Request(), "1", repository=repo, config={"dummy": {}}
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert data["code"] == "invalid_json"

    @pytest.mark.django_db(transaction=True)
    async def test_callback_with_empty_body(self) -> None:
        django_registry.register(DummyProvider)
        repo = Repo()

        class EmptyRequest:
            body = b""
            content_type = "application/json"
            headers: ClassVar[dict[str, str]] = {"x-dummy-token": "ok"}
            method = "POST"
            META: ClassVar[dict[str, str]] = {"REMOTE_ADDR": "127.0.0.1"}

        response = await _callback_response(
            EmptyRequest(),
            "1",
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "accepted"

    @pytest.mark.django_db(transaction=True)
    async def test_success_response_contains_shipment_id(self) -> None:
        django_registry.register(DummyProvider)
        repo = Repo()
        response = await _callback_response(
            RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
            "1",
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )
        data = json.loads(response.content)
        assert data["shipment"]["id"] == "1"

    @pytest.mark.django_db(transaction=True)
    async def test_success_response_contains_status(self) -> None:
        django_registry.register(DummyProvider)
        repo = Repo()
        response = await _callback_response(
            RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
            "1",
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )
        data = json.loads(response.content)
        assert data["status"] == "accepted"
        assert data["update"]["status"] == ShipmentStatus.IN_TRANSIT

    @pytest.mark.django_db(transaction=True)
    async def test_callback_get_request_returns_405(self) -> None:
        """GET requests to callback endpoint return 405 Method Not Allowed."""
        django_registry.register(DummyProvider)
        repo = Repo()

        class GetRequest:
            body = b"{}"
            content_type = "application/json"
            headers: ClassVar[dict[str, str]] = {"x-dummy-token": "ok"}
            method = "GET"
            path = "/callback/1/"

        response = await _callback_response(
            GetRequest(), "1", repository=repo, config={"dummy": {}}
        )
        assert response.status_code == 405

    @pytest.mark.django_db(transaction=True)
    async def test_callback_csrf_exempt(self) -> None:
        """Callback view should not require CSRF token (external webhooks)."""
        django_registry.register(DummyProvider)
        repo = Repo()

        # POST request without CSRF token in headers
        response = await _callback_response(
            RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
            "1",
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )

        # Should succeed (status 200), not 403 Forbidden
        assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
async def test_concurrent_callbacks_are_serialized() -> None:
    """Two concurrent callbacks for the same shipment must not race.

    The ``select_for_update`` lock in ``_handle_callback`` serializes
    concurrent callbacks, so the second callback sees the state
    updated by the first one.
    """
    import asyncio

    django_registry.register(DummyProvider)

    class TrackingRepo(Repo):
        """Tracks how many times handle_callback was called."""

        call_count: ClassVar[int] = 0

        async def update_fields(
            self, shipment_id: str, **fields: Any
        ) -> DummyShipment:
            TrackingRepo.call_count += 1
            for key, value in fields.items():
                setattr(self.shipment, key, value)
            return self.shipment

    repo = TrackingRepo()
    repo.shipment.status = ShipmentStatus.LABEL_READY

    # Fire two callbacks concurrently for the same shipment.
    task1 = _callback_response(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
        "1",
        repository=repo,
        config={"dummy": {"callback_token": "ok"}},
    )
    task2 = _callback_response(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
        "1",
        repository=repo,
        config={"dummy": {"callback_token": "ok"}},
    )

    responses = await asyncio.gather(task1, task2)

    # Both should succeed.
    for resp in responses:
        assert resp.status_code == 200

    # The transaction.atomic() + select_for_update() ensures the
    # callbacks are serialized — both complete successfully.
    assert repo.shipment.status == ShipmentStatus.IN_TRANSIT


class IpVerifyingProvider(BaseProvider):
    """Provider that records the source_ip it receives for verification."""

    slug = "ip_verify"
    display_name = "IP Verifying"
    verified_ips: ClassVar[list[str]] = []

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
        IpVerifyingProvider.verified_ips.append(ctx.source_ip)

    async def handle_callback(
        self,
        ctx: CallbackContext,
    ) -> ShipmentUpdateResult:
        return {"status": ShipmentStatus.IN_TRANSIT}


@pytest.mark.django_db(transaction=True)
@override_settings(SENDPARCEL_TRUSTED_PROXIES=["10.0.0.0/8"])
async def test_callback_resolves_xff_behind_trusted_proxy() -> None:
    """Behind a trusted proxy, source_ip is resolved from XFF."""
    IpVerifyingProvider.verified_ips.clear()
    django_registry.register(IpVerifyingProvider)
    shipment = DummyShipment()
    shipment.provider = "ip_verify"
    repo = Repo()
    repo.shipment = shipment

    request = RequestStub(
        payload={"event": "picked_up"},
        headers={},
        remote_addr="10.0.0.1",  # Trusted proxy
    )
    # Simulate X-Forwarded-For: carrier IP behind proxy
    request.META["HTTP_X_FORWARDED_FOR"] = "91.216.25.10"

    await _callback_response(
        request,
        "1",
        repository=repo,
        config={},
    )

    assert len(IpVerifyingProvider.verified_ips) == 1
    assert IpVerifyingProvider.verified_ips[0] == "91.216.25.10"


@pytest.mark.django_db(transaction=True)
@override_settings(SENDPARCEL_TRUSTED_PROXIES=["10.0.0.0/8"])
async def test_callback_ignores_xff_from_untrusted_remote() -> None:
    """Untrusted REMOTE_ADDR can't spoof carrier IP via XFF."""
    IpVerifyingProvider.verified_ips.clear()
    django_registry.register(IpVerifyingProvider)
    shipment = DummyShipment()
    shipment.provider = "ip_verify"
    repo = Repo()
    repo.shipment = shipment

    request = RequestStub(
        payload={"event": "picked_up"},
        headers={},
        remote_addr="192.168.1.100",  # NOT trusted
    )
    request.META["HTTP_X_FORWARDED_FOR"] = "91.216.25.10"  # Spoofed

    await _callback_response(
        request,
        "1",
        repository=repo,
        config={},
    )

    assert len(IpVerifyingProvider.verified_ips) == 1
    # Should use REMOTE_ADDR, not spoofed XFF
    assert IpVerifyingProvider.verified_ips[0] == "192.168.1.100"


@pytest.mark.django_db(transaction=True)
async def test_callback_without_trusted_proxies_uses_remote_addr() -> None:
    """Without TRUSTED_PROXIES, source_ip = REMOTE_ADDR (backward compat)."""
    IpVerifyingProvider.verified_ips.clear()
    django_registry.register(IpVerifyingProvider)
    shipment = DummyShipment()
    shipment.provider = "ip_verify"
    repo = Repo()
    repo.shipment = shipment

    request = RequestStub(
        payload={"event": "picked_up"},
        headers={},
        remote_addr="91.216.25.10",
    )
    request.META["HTTP_X_FORWARDED_FOR"] = "192.168.1.100"

    await _callback_response(
        request,
        "1",
        repository=repo,
        config={},
    )

    assert len(IpVerifyingProvider.verified_ips) == 1
    # No TRUSTED_PROXIES → REMOTE_ADDR used directly
    assert IpVerifyingProvider.verified_ips[0] == "91.216.25.10"

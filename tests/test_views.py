"""View tests."""

import json
from typing import Any, ClassVar, cast

from sendparcel.enums import ShipmentStatus
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
    ShipmentNotFoundError,
)
from sendparcel.provider import BaseProvider, PushCallbackProvider
from sendparcel.types import ShipmentCreateResult, ShipmentUpdateResult
from sendparcel_django.registry import registry as django_registry
from sendparcel_django.views import callback


class DummyShipment:
    id = 1
    status = ShipmentStatus.LABEL_READY
    provider = "dummy"
    external_id = ""
    tracking_number = "TRK-TEST"


class DummyProvider(BaseProvider, PushCallbackProvider):
    slug = "dummy"
    display_name = "Dummy"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ) -> ShipmentCreateResult:
        return {"external_id": "ext-1"}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        if headers.get("x-dummy-token") != "ok":
            raise InvalidCallbackError("BAD TOKEN")

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> ShipmentUpdateResult:
        return {"status": ShipmentStatus.IN_TRANSIT}


class Repo:
    def __init__(self) -> None:
        self.shipment = DummyShipment()

    async def get_by_id(self, shipment_id: str):
        return self.shipment

    async def create(self, **kwargs):
        raise NotImplementedError

    async def save(self, shipment):
        self.shipment = shipment
        return shipment

    async def update_status(self, shipment_id: str, status: str, **fields):
        raise NotImplementedError


class RequestStub:
    def __init__(self, payload: dict, headers: dict):
        self.body = json.dumps(payload).encode("utf-8")
        self.headers = headers
        self.method = "POST"


def _callback_response(
    request: Any,
    shipment_id: str,
    *,
    repository: Any,
    config: dict[str, Any],
):
    return callback(
        cast(Any, request),
        shipment_id,
        repository=repository,
        config=config,
    )


def test_callback_uses_flow_and_updates_status() -> None:
    django_registry.register(DummyProvider)
    repo = Repo()

    response = _callback_response(
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


def test_callback_returns_bad_request_on_invalid_signature() -> None:
    django_registry.register(DummyProvider)
    repo = Repo()

    response = _callback_response(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "bad"}),
        "1",
        repository=repo,
        config={"dummy": {"callback_token": "ok"}},
    )

    assert response.status_code == 400
    data = json.loads(response.content)
    assert data["code"] == "invalid_callback"


class CommunicationErrorProvider(BaseProvider, PushCallbackProvider):
    slug = "comm_err"
    display_name = "CommErr"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ) -> ShipmentCreateResult:
        return {"external_id": "ext-1"}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        raise CommunicationError("Provider API unreachable")

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> ShipmentUpdateResult:
        return {}


class TransitionErrorProvider(BaseProvider, PushCallbackProvider):
    slug = "trans_err"
    display_name = "TransErr"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ) -> ShipmentCreateResult:
        return {"external_id": "ext-1"}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        pass

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> ShipmentUpdateResult:
        raise InvalidTransitionError("Cannot transition from current state")


class GenericErrorProvider(BaseProvider, PushCallbackProvider):
    slug = "generic_err"
    display_name = "GenericErr"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ) -> ShipmentCreateResult:
        return {"external_id": "ext-1"}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        pass

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> ShipmentUpdateResult:
        raise SendParcelException("Something went wrong")


class NoCallbackProvider(BaseProvider):
    slug = "no-callback"
    display_name = "No Callback"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ) -> ShipmentCreateResult:
        return {"external_id": "ext-1"}


def test_callback_returns_502_on_communication_error() -> None:
    django_registry.register(CommunicationErrorProvider)
    shipment = DummyShipment()
    shipment.provider = "comm_err"
    repo = Repo()
    repo.shipment = shipment

    response = _callback_response(
        RequestStub({"event": "status_update"}, {}),
        "1",
        repository=repo,
        config={},
    )

    assert response.status_code == 502
    data = json.loads(response.content)
    assert data["code"] == "communication_error"
    assert "Provider API unreachable" in data["detail"]


def test_callback_returns_409_on_invalid_transition() -> None:
    django_registry.register(TransitionErrorProvider)
    shipment = DummyShipment()
    shipment.provider = "trans_err"
    repo = Repo()
    repo.shipment = shipment

    response = _callback_response(
        RequestStub({"event": "status_update"}, {}),
        "1",
        repository=repo,
        config={},
    )

    assert response.status_code == 409
    data = json.loads(response.content)
    assert data["code"] == "invalid_transition"
    assert "Cannot transition from current state" in data["detail"]


def test_callback_returns_400_on_generic_sendparcel_exception() -> None:
    django_registry.register(GenericErrorProvider)
    shipment = DummyShipment()
    shipment.provider = "generic_err"
    repo = Repo()
    repo.shipment = shipment

    response = _callback_response(
        RequestStub({"event": "status_update"}, {}),
        "1",
        repository=repo,
        config={},
    )

    assert response.status_code == 400
    data = json.loads(response.content)
    assert data["code"] == "sendparcel_error"
    assert "Something went wrong" in data["detail"]


def test_callback_returns_404_when_shipment_is_missing() -> None:
    class MissingRepo(Repo):
        async def get_by_id(self, shipment_id: str):
            raise ShipmentNotFoundError(shipment_id)

    django_registry.register(DummyProvider)

    response = _callback_response(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
        "1",
        repository=MissingRepo(),
        config={"dummy": {"callback_token": "ok"}},
    )

    assert response.status_code == 404
    data = json.loads(response.content)
    assert data["code"] == "shipment_not_found"


def test_callback_returns_404_when_provider_is_missing() -> None:
    repo = Repo()
    repo.shipment.provider = "missing-provider"

    response = _callback_response(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
        "1",
        repository=repo,
        config={},
    )

    assert response.status_code == 404
    data = json.loads(response.content)
    assert data["code"] == "provider_not_found"
    assert "missing-provider" in data["detail"]


def test_callback_returns_409_when_provider_lacks_callback_support() -> None:
    django_registry.register(NoCallbackProvider)
    repo = Repo()
    repo.shipment.provider = "no-callback"

    response = _callback_response(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
        "1",
        repository=repo,
        config={},
    )

    assert response.status_code == 409
    data = json.loads(response.content)
    assert data["code"] == "provider_capability_error"
    assert "does not support push callbacks" in data["detail"]


def test_callback_auto_creates_repository_when_none_provided() -> None:
    django_registry.register(DummyProvider)
    repo = Repo()

    response = _callback_response(
        RequestStub({}, {"x-dummy-token": "ok"}),
        "1",
        repository=repo,
        config={"dummy": {"callback_token": "ok"}},
    )

    assert b"Repository is required" not in response.content


class TestCallbackEdgeCases:
    def test_callback_with_invalid_json(self) -> None:
        django_registry.register(DummyProvider)
        repo = Repo()

        class BadJsonRequest:
            body = b"not-json{{"
            headers: ClassVar[dict] = {"x-dummy-token": "ok"}
            method = "POST"

        response = _callback_response(
            BadJsonRequest(), "1", repository=repo, config={"dummy": {}}
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert "Invalid JSON" in data["detail"]
        assert data["code"] == "invalid_json"

    def test_callback_with_invalid_utf8(self) -> None:
        django_registry.register(DummyProvider)
        repo = Repo()

        class BadUtf8Request:
            body = b"\x80\x81\x82"
            headers: ClassVar[dict] = {"x-dummy-token": "ok"}
            method = "POST"

        response = _callback_response(
            BadUtf8Request(), "1", repository=repo, config={"dummy": {}}
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert data["code"] == "invalid_json"

    def test_callback_with_empty_body(self) -> None:
        django_registry.register(DummyProvider)
        repo = Repo()

        class EmptyRequest:
            body = b""
            headers: ClassVar[dict] = {"x-dummy-token": "ok"}
            method = "POST"

        response = _callback_response(
            EmptyRequest(),
            "1",
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "accepted"

    def test_success_response_contains_shipment_id(self) -> None:
        django_registry.register(DummyProvider)
        repo = Repo()
        response = _callback_response(
            RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
            "1",
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )
        data = json.loads(response.content)
        assert data["shipment"]["id"] == "1"

    def test_success_response_contains_status(self) -> None:
        django_registry.register(DummyProvider)
        repo = Repo()
        response = _callback_response(
            RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
            "1",
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )
        data = json.loads(response.content)
        assert data["status"] == "accepted"
        assert data["update"]["status"] == ShipmentStatus.IN_TRANSIT

    def test_callback_get_request_returns_405(self) -> None:
        """GET requests to callback endpoint return 405 Method Not Allowed."""
        django_registry.register(DummyProvider)
        repo = Repo()

        class GetRequest:
            body = b"{}"
            headers: ClassVar[dict] = {"x-dummy-token": "ok"}
            method = "GET"
            path = "/callback/1/"

        response = _callback_response(
            GetRequest(), "1", repository=repo, config={"dummy": {}}
        )
        assert response.status_code == 405

    def test_callback_csrf_exempt(self) -> None:
        """Callback view should not require CSRF token (external webhooks)."""
        django_registry.register(DummyProvider)
        repo = Repo()

        # POST request without CSRF token in headers
        response = _callback_response(
            RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
            "1",
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )

        # Should succeed (status 200), not 403 Forbidden
        assert response.status_code == 200

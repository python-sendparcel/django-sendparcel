"""View tests."""

import json
from typing import ClassVar

from sendparcel.enums import ShipmentStatus
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
)
from sendparcel.provider import BaseProvider, PushCallbackProvider
from sendparcel.registry import registry as core_registry
from sendparcel_django.views import callback


class DummyShipment:
    id = 1
    status = ShipmentStatus.LABEL_READY
    provider = "dummy"
    external_id = ""
    tracking_number = "TRK-TEST"
    label_url = ""


class DummyProvider(BaseProvider, PushCallbackProvider):
    slug = "dummy"
    display_name = "Dummy"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        if headers.get("x-dummy-token") != "ok":
            raise InvalidCallbackError("BAD TOKEN")

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        if self.shipment.may_trigger("mark_in_transit"):
            self.shipment.mark_in_transit()


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


def test_callback_uses_flow_and_updates_status() -> None:
    core_registry.register(DummyProvider)
    repo = Repo()

    response = callback(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
        1,
        repository=repo,
        config={"dummy": {"callback_token": "ok"}},
    )

    assert response.status_code == 200
    assert b'"status": "in_transit"' in response.content


def test_callback_returns_bad_request_on_invalid_signature() -> None:
    core_registry.register(DummyProvider)
    repo = Repo()

    response = callback(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "bad"}),
        1,
        repository=repo,
        config={"dummy": {"callback_token": "ok"}},
    )

    assert response.status_code == 400


class CommunicationErrorProvider(BaseProvider, PushCallbackProvider):
    slug = "comm_err"
    display_name = "CommErr"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        raise CommunicationError("Provider API unreachable")

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        pass


class TransitionErrorProvider(BaseProvider, PushCallbackProvider):
    slug = "trans_err"
    display_name = "TransErr"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        pass

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        raise InvalidTransitionError("Cannot transition from current state")


class GenericErrorProvider(BaseProvider, PushCallbackProvider):
    slug = "generic_err"
    display_name = "GenericErr"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        pass

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        raise SendParcelException("Something went wrong")


def test_callback_returns_502_on_communication_error() -> None:
    core_registry.register(CommunicationErrorProvider)
    shipment = DummyShipment()
    shipment.provider = "comm_err"
    repo = Repo()
    repo.shipment = shipment

    response = callback(
        RequestStub({"event": "status_update"}, {}),
        1,
        repository=repo,
        config={},
    )

    assert response.status_code == 502
    assert b"Provider API unreachable" in response.content


def test_callback_returns_409_on_invalid_transition() -> None:
    core_registry.register(TransitionErrorProvider)
    shipment = DummyShipment()
    shipment.provider = "trans_err"
    repo = Repo()
    repo.shipment = shipment

    response = callback(
        RequestStub({"event": "status_update"}, {}),
        1,
        repository=repo,
        config={},
    )

    assert response.status_code == 409
    assert b"Cannot transition from current state" in response.content


def test_callback_returns_400_on_generic_sendparcel_exception() -> None:
    core_registry.register(GenericErrorProvider)
    shipment = DummyShipment()
    shipment.provider = "generic_err"
    repo = Repo()
    repo.shipment = shipment

    response = callback(
        RequestStub({"event": "status_update"}, {}),
        1,
        repository=repo,
        config={},
    )

    assert response.status_code == 400
    assert b"Something went wrong" in response.content


def test_callback_auto_creates_repository_when_none_provided() -> None:
    core_registry.register(DummyProvider)
    repo = Repo()

    response = callback(
        RequestStub({}, {"x-dummy-token": "ok"}),
        1,
        repository=repo,
        config={"dummy": {"callback_token": "ok"}},
    )

    assert b"Repository is required" not in response.content


class TestCallbackEdgeCases:
    def test_callback_with_invalid_json(self) -> None:
        core_registry.register(DummyProvider)
        repo = Repo()

        class BadJsonRequest:
            body = b"not-json{{"
            headers: ClassVar[dict] = {"x-dummy-token": "ok"}
            method = "POST"

        response = callback(
            BadJsonRequest(), 1, repository=repo, config={"dummy": {}}
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert "Invalid JSON" in data["detail"]

    def test_callback_with_invalid_utf8(self) -> None:
        core_registry.register(DummyProvider)
        repo = Repo()

        class BadUtf8Request:
            body = b"\x80\x81\x82"
            headers: ClassVar[dict] = {"x-dummy-token": "ok"}
            method = "POST"

        response = callback(
            BadUtf8Request(), 1, repository=repo, config={"dummy": {}}
        )
        assert response.status_code == 400

    def test_callback_with_empty_body(self) -> None:
        core_registry.register(DummyProvider)
        repo = Repo()

        class EmptyRequest:
            body = b""
            headers: ClassVar[dict] = {"x-dummy-token": "ok"}
            method = "POST"

        response = callback(
            EmptyRequest(),
            1,
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )
        assert response.status_code == 200

    def test_success_response_contains_shipment_id(self) -> None:
        core_registry.register(DummyProvider)
        repo = Repo()
        response = callback(
            RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
            1,
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )
        data = json.loads(response.content)
        assert "shipment_id" in data
        assert data["received"] is True

    def test_success_response_contains_status(self) -> None:
        core_registry.register(DummyProvider)
        repo = Repo()
        response = callback(
            RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
            1,
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )
        data = json.loads(response.content)
        assert "status" in data

    def test_callback_get_request_returns_405(self) -> None:
        """GET requests to callback endpoint return 405 Method Not Allowed."""
        core_registry.register(DummyProvider)
        repo = Repo()

        class GetRequest:
            body = b"{}"
            headers: ClassVar[dict] = {"x-dummy-token": "ok"}
            method = "GET"
            path = "/callback/1/"

        response = callback(
            GetRequest(), 1, repository=repo, config={"dummy": {}}
        )
        assert response.status_code == 405

    def test_callback_csrf_exempt(self) -> None:
        """Callback view should not require CSRF token (external webhooks)."""
        core_registry.register(DummyProvider)
        repo = Repo()

        # POST request without CSRF token in headers
        response = callback(
            RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
            1,
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )

        # Should succeed (status 200), not 403 Forbidden
        assert response.status_code == 200

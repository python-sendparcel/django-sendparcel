"""View tests."""

import json

from sendparcel.enums import ShipmentStatus
from sendparcel.exceptions import InvalidCallbackError
from sendparcel.provider import BaseProvider
from sendparcel.registry import registry as core_registry
from sendparcel_django.views import callback


class DummyShipment:
    id = "s-1"
    order = object()
    status = ShipmentStatus.LABEL_READY
    provider = "dummy"
    external_id = ""
    tracking_number = ""
    label_url = ""


class DummyProvider(BaseProvider):
    slug = "dummy"
    display_name = "Dummy"

    async def create_shipment(self, **kwargs):
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


def test_callback_uses_flow_and_updates_status() -> None:
    core_registry.register(DummyProvider)
    repo = Repo()

    response = callback(
        RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
        "s-1",
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
        "s-1",
        repository=repo,
        config={"dummy": {"callback_token": "ok"}},
    )

    assert response.status_code == 400

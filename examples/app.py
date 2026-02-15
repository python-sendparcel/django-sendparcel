"""Django example callback integration using built-in dummy provider."""

from __future__ import annotations

import json
from dataclasses import dataclass

from django.urls import path

from sendparcel.providers.dummy import DummyProvider
from sendparcel.registry import registry
from sendparcel_django.views import callback

DEFAULT_PROVIDER = DummyProvider.slug


@dataclass
class DemoOrder:
    id: str

    def get_total_weight(self):
        return 1

    def get_parcels(self):
        return []

    def get_sender_address(self):
        return {"country_code": "PL"}

    def get_receiver_address(self):
        return {"country_code": "DE"}


@dataclass
class DemoShipment:
    id: str
    order: DemoOrder
    status: str
    provider: str
    external_id: str = ""
    tracking_number: str = ""
    label_url: str = ""


class InMemoryRepo:
    def __init__(self) -> None:
        self.items: dict[str, DemoShipment] = {}
        self._counter = 0

    async def get_by_id(self, shipment_id: str) -> DemoShipment:
        return self.items[shipment_id]

    async def create(self, **kwargs) -> DemoShipment:
        self._counter += 1
        shipment_id = f"s-{self._counter}"
        shipment = DemoShipment(
            id=shipment_id,
            order=kwargs["order"],
            provider=kwargs["provider"],
            status=str(kwargs["status"]),
        )
        self.items[shipment_id] = shipment
        return shipment

    async def save(self, shipment: DemoShipment) -> DemoShipment:
        self.items[shipment.id] = shipment
        return shipment

    async def update_status(
        self, shipment_id: str, status: str, **fields
    ) -> DemoShipment:
        shipment = self.items[shipment_id]
        shipment.status = status
        for key, value in fields.items():
            setattr(shipment, key, value)
        return shipment


class RequestStub:
    def __init__(self, payload: dict, headers: dict):
        self.body = json.dumps(payload).encode("utf-8")
        self.headers = headers


registry.register(DummyProvider)
repository = InMemoryRepo()


def seed_shipment() -> str:
    shipment_id = f"s-{len(repository.items) + 1}"
    repository.items[shipment_id] = DemoShipment(
        id=shipment_id,
        order=DemoOrder(id="o-1"),
        status="label_ready",
        provider=DEFAULT_PROVIDER,
    )
    return shipment_id


def callback_endpoint(request, shipment_id: str):
    return callback(
        request,
        shipment_id,
        repository=repository,
        config={DEFAULT_PROVIDER: {"callback_token": "dummy-token"}},
    )


urlpatterns = [
    path("callback/<str:shipment_id>/", callback_endpoint, name="callback")
]

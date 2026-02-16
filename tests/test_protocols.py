"""Protocol adapter tests."""

from sendparcel_django.protocols import (
    DjangoOrderAdapter,
    DjangoShipmentAdapter,
)


class OrderObj:
    id = 42
    amount_weight = 2.5

    def get_total_weight(self):
        return self.amount_weight

    def get_parcels(self):
        return [{"weight_kg": 2.5}]

    def get_sender_address(self):
        return {"country_code": "PL"}

    def get_receiver_address(self):
        return {"country_code": "DE"}


class ShipmentObj:
    id = "ship-1"
    order = OrderObj()
    status = "created"
    provider = "dummy"
    external_id = "ext-1"
    tracking_number = "trk-1"
    label_url = "https://labels/1.pdf"


def test_order_adapter_delegates_order_methods() -> None:
    adapter = DjangoOrderAdapter(OrderObj())

    assert adapter.get_total_weight() == 2.5
    assert adapter.get_sender_address()["country_code"] == "PL"


def test_order_adapter_exposes_id() -> None:
    adapter = DjangoOrderAdapter(OrderObj())

    assert adapter.id == 42


def test_shipment_adapter_exposes_core_fields() -> None:
    adapter = DjangoShipmentAdapter(ShipmentObj())

    assert adapter.id == "ship-1"
    assert adapter.provider == "dummy"
    assert adapter.label_url.endswith("1.pdf")

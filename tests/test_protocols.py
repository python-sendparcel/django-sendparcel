"""Protocol adapter tests."""

from sendparcel_django.protocols import DjangoShipmentAdapter


class ShipmentObj:
    id = "ship-1"
    status = "created"
    provider = "dummy"
    external_id = "ext-1"
    tracking_number = "trk-1"
    label_url = "https://labels/1.pdf"


def test_shipment_adapter_exposes_core_fields() -> None:
    adapter = DjangoShipmentAdapter(ShipmentObj())

    assert adapter.id == "ship-1"
    assert adapter.provider == "dummy"
    assert adapter.label_url.endswith("1.pdf")

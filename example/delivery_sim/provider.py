"""Delivery simulator provider — a fake carrier for the example project."""

from typing import ClassVar

from sendparcel.exceptions import InvalidCallbackError
from sendparcel.fsm import STATUS_TO_CALLBACK
from sendparcel.provider import BaseProvider
from sendparcel.types import (
    LabelInfo,
    ShipmentCreateResult,
    ShipmentStatusResponse,
)


class DeliverySimProvider(BaseProvider):
    """Fake delivery provider for local development and demos."""

    slug: ClassVar[str] = "delivery-sim"
    display_name: ClassVar[str] = "Symulator Dostawy"
    supported_countries: ClassVar[list[str]] = ["PL"]
    supported_services: ClassVar[list[str]] = ["standard"]
    user_selectable: ClassVar[bool] = False

    async def create_shipment(self, **kwargs) -> ShipmentCreateResult:
        shipment_id = str(self.shipment.id)
        return ShipmentCreateResult(
            external_id=f"SIM-{shipment_id}",
            tracking_number=f"SIM-TRK-{shipment_id}",
            label=LabelInfo(
                format="PDF",
                url=self._label_url(shipment_id),
            ),
        )

    async def create_label(self, **kwargs) -> LabelInfo:
        shipment_id = str(self.shipment.id)
        return LabelInfo(
            format="PDF",
            url=self._label_url(shipment_id),
        )

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        expected_token = self.get_setting(
            "callback_token", "example-sim-token-12345"
        )
        provided_token = headers.get("x-sim-token", "")
        if provided_token != expected_token:
            raise InvalidCallbackError(
                "Nieprawidłowy token zwrotny symulatora."
            )

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        status_value = data.get("status")
        if not status_value:
            return

        callback = STATUS_TO_CALLBACK.get(str(status_value), str(status_value))
        trigger = getattr(self.shipment, callback, None)
        may_trigger = getattr(self.shipment, "may_trigger", None)
        if trigger is None or may_trigger is None:
            return
        if may_trigger(callback):
            trigger()

    async def fetch_shipment_status(self, **kwargs) -> ShipmentStatusResponse:
        return ShipmentStatusResponse(
            status=self.shipment.status,
        )

    async def cancel_shipment(self, **kwargs) -> bool:
        return True

    def _label_url(self, shipment_id: str) -> str:
        base = self.get_setting(
            "api_url", "http://localhost:8000/delivery-sim/"
        )
        return f"{str(base).rstrip('/')}/label/{shipment_id}.pdf"

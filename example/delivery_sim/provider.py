"""Delivery simulator provider — a fake carrier for the example project."""

from __future__ import annotations

from typing import Any, ClassVar
from uuid import uuid4

from sendparcel.enums import LabelFormat, ShipmentStatus
from sendparcel.provider import (
    BaseProvider,
    CancellableProvider,
    LabelProvider,
    PullStatusProvider,
)
from sendparcel.types import (
    AddressInfo,
    LabelInfo,
    ParcelInfo,
    ShipmentCreateResult,
    ShipmentUpdateResult,
)

# Global in-memory simulator state
_sim_state: dict[str, str] = {}


# Allowed forward transitions for the control panel
_NEXT_STATUSES: dict[str, list[str]] = {
    ShipmentStatus.CREATED: [
        ShipmentStatus.LABEL_READY,
        ShipmentStatus.CANCELLED,
        ShipmentStatus.FAILED,
    ],
    ShipmentStatus.LABEL_READY: [
        ShipmentStatus.IN_TRANSIT,
        ShipmentStatus.CANCELLED,
        ShipmentStatus.FAILED,
    ],
    ShipmentStatus.IN_TRANSIT: [
        ShipmentStatus.OUT_FOR_DELIVERY,
        ShipmentStatus.DELIVERED,
        ShipmentStatus.RETURNED,
        ShipmentStatus.FAILED,
    ],
    ShipmentStatus.OUT_FOR_DELIVERY: [
        ShipmentStatus.DELIVERED,
        ShipmentStatus.RETURNED,
        ShipmentStatus.FAILED,
    ],
}


def get_sim_status(shipment_id: str) -> str:
    return _sim_state.get(shipment_id, ShipmentStatus.NEW)


def update_sim_status(shipment_id: str, status: str) -> None:
    _sim_state[shipment_id] = status


def get_next_statuses(current: str) -> list[str]:
    return _NEXT_STATUSES.get(current, [])


class DeliverySimProvider(
    BaseProvider,
    LabelProvider,
    PullStatusProvider,
    CancellableProvider,
):
    """Fake delivery provider for local development and demos."""

    slug: ClassVar[str] = "delivery-sim"
    display_name: ClassVar[str] = "Delivery Simulator"
    supported_countries: ClassVar[list[str]] = ["PL"]
    supported_services: ClassVar[list[str]] = ["standard"]
    user_selectable: ClassVar[bool] = True

    async def create_shipment(
        self,
        *,
        sender_address: AddressInfo,
        receiver_address: AddressInfo,
        parcels: list[ParcelInfo],
        **kwargs: Any,
    ) -> ShipmentCreateResult:
        shipment_id = self._shipment_id()
        tracking = f"SIM-{uuid4().hex[:8].upper()}"
        _sim_state[shipment_id] = ShipmentStatus.CREATED

        return ShipmentCreateResult(
            external_id=f"SIM-{shipment_id}",
            tracking_number=tracking,
            label=LabelInfo(
                format=LabelFormat.PDF,
                url=self._label_url(shipment_id),
            ),
        )

    async def create_label(self, **kwargs: Any) -> LabelInfo:
        shipment_id = self._shipment_id()
        return LabelInfo(
            format=LabelFormat.PDF,
            url=self._label_url(shipment_id),
        )

    async def fetch_shipment_status(
        self, **kwargs: Any
    ) -> ShipmentUpdateResult:
        shipment_id = self._shipment_id()
        # Default to current status if not in sim state
        current = _sim_state.get(shipment_id, str(self.shipment.status))
        return ShipmentUpdateResult(status=current)

    async def cancel_shipment(self, **kwargs: Any) -> bool:
        shipment_id = self._shipment_id()
        _sim_state[shipment_id] = ShipmentStatus.CANCELLED
        return True

    def _shipment_id(self) -> str:
        shipment_pk = getattr(self.shipment, "pk", self.shipment.id)
        return str(shipment_pk)

    def _label_url(self, shipment_id: str) -> str:
        # We assume the app is running on localhost:8000 for this demo
        # ideally this should come from settings or reverse()
        # but provider runs in a context where reverse() might not be
        # available cleanly without request
        # However, for this example app, we can hardcode the path
        # relative to root if used in browser
        return f"/delivery-sim/label/{shipment_id}.pdf"

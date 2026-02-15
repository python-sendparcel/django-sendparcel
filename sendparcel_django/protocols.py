"""Protocol adapters for Django domain objects."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class DjangoOrderAdapter:
    """Adapter exposing core order protocol from a Django model instance."""

    wrapped: Any

    def get_total_weight(self) -> Decimal:
        return Decimal(str(self.wrapped.get_total_weight()))

    def get_parcels(self) -> list[dict]:
        return list(self.wrapped.get_parcels())

    def get_sender_address(self) -> dict:
        return dict(self.wrapped.get_sender_address())

    def get_receiver_address(self) -> dict:
        return dict(self.wrapped.get_receiver_address())


@dataclass
class DjangoShipmentAdapter:
    """Adapter exposing core shipment protocol from a Django model instance."""

    wrapped: Any

    @property
    def id(self) -> str:
        return str(self.wrapped.id)

    @property
    def order(self) -> Any:
        return self.wrapped.order

    @property
    def status(self) -> str:
        return str(self.wrapped.status)

    @status.setter
    def status(self, value: str) -> None:
        self.wrapped.status = value

    @property
    def provider(self) -> str:
        return str(self.wrapped.provider)

    @property
    def external_id(self) -> str:
        return str(self.wrapped.external_id)

    @external_id.setter
    def external_id(self, value: str) -> None:
        self.wrapped.external_id = value

    @property
    def tracking_number(self) -> str:
        return str(self.wrapped.tracking_number)

    @tracking_number.setter
    def tracking_number(self, value: str) -> None:
        self.wrapped.tracking_number = value

    @property
    def label_url(self) -> str:
        return str(self.wrapped.label_url)

    @label_url.setter
    def label_url(self, value: str) -> None:
        self.wrapped.label_url = value

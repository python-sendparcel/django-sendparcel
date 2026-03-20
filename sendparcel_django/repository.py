"""Django ORM repository for shipment persistence."""

from __future__ import annotations

from typing import Any, cast

import swapper
from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from sendparcel.exceptions import ShipmentNotFoundError

from sendparcel_django.protocols import DjangoShipmentAdapter


class DjangoShipmentRepository:
    """Repository wrapping Django ORM with sync_to_async."""

    def _get_model(self) -> type[models.Model]:
        return cast(
            type[models.Model],
            swapper.load_model("sendparcel_django", "Shipment"),
        )

    async def get_by_id(self, shipment_id: str) -> Any:
        """Fetch a shipment by primary key."""
        model = self._get_model()
        try:
            return await sync_to_async(model._default_manager.get)(
                pk=shipment_id
            )
        except ObjectDoesNotExist as e:
            raise ShipmentNotFoundError(shipment_id) from e

    async def create(self, **kwargs: Any) -> Any:
        """Create a new shipment record."""
        model = self._get_model()
        return await sync_to_async(model._default_manager.create)(**kwargs)

    async def save(self, shipment: Any) -> Any:
        """Persist changes on an existing shipment instance."""
        model_instance = self._unwrap_shipment(shipment)
        await sync_to_async(model_instance.save)()
        return model_instance

    async def update_status(
        self, shipment_id: str, status: str, **fields: Any
    ) -> Any:
        """Update the status (and optional extra fields) of a shipment."""
        shipment = await self.get_by_id(shipment_id)
        shipment.status = status
        for key, value in fields.items():
            setattr(shipment, key, value)
        await sync_to_async(shipment.save)()
        return shipment

    def _unwrap_shipment(self, shipment: Any) -> Any:
        if isinstance(shipment, DjangoShipmentAdapter):
            return shipment.wrapped
        return shipment

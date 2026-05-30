"""Django ORM repository for shipment persistence."""

from __future__ import annotations

from typing import Any, cast

import swapper
from asgiref.sync import sync_to_async
from django.db import models, transaction
from sendparcel.exceptions import ShipmentNotFoundError

from sendparcel_django.protocols import DjangoShipmentAdapter


class DjangoShipmentRepository:
    """Repository wrapping Django ORM with sync_to_async.

    All read-modify-write operations should be wrapped in
    ``transaction.atomic()`` with ``select_for_update()`` by the
    caller to prevent race conditions on concurrent webhook callbacks.
    """

    def _get_model(self) -> type[models.Model]:
        return swapper.load_model("sendparcel_django", "Shipment")  # type: ignore[no-any-return]

    def _wrap(self, obj: models.Model) -> DjangoShipmentAdapter:
        """Wrap a Django model instance in a protocol adapter."""
        return DjangoShipmentAdapter(obj)

    async def get_by_id(
        self, shipment_id: str, *, for_update: bool = False
    ) -> DjangoShipmentAdapter:
        """Fetch a shipment by primary key.

        Args:
            shipment_id: Primary key of the shipment.
            for_update: If True, use ``select_for_update()`` to lock
                the row for concurrent-write safety.
        """
        model = self._get_model()
        qs = model._default_manager.filter(pk=shipment_id)
        if for_update:
            qs = qs.select_for_update()
        obj = await sync_to_async(qs.first)()
        if obj is None:
            raise ShipmentNotFoundError(shipment_id)
        return self._wrap(obj)

    async def create(self, **kwargs: Any) -> DjangoShipmentAdapter:
        """Create a new shipment record."""
        model = self._get_model()
        obj = await sync_to_async(model._default_manager.create)(**kwargs)
        return self._wrap(obj)

    async def save(self, shipment: Any) -> DjangoShipmentAdapter:
        """Persist changes on an existing shipment instance."""
        model_instance = self._unwrap_shipment(shipment)
        await sync_to_async(model_instance.save)()
        return self._wrap(model_instance)

    async def update_status(
        self, shipment_id: str, status: str, **fields: Any
    ) -> DjangoShipmentAdapter:
        """Update the status (and optional extra fields) of a shipment."""
        shipment = await self.get_by_id(shipment_id)
        shipment.status = status
        for key, value in fields.items():
            setattr(shipment, key, value)
        await sync_to_async(shipment.save)()
        return shipment

    async def delete(self, shipment_id: str) -> None:
        """Delete a shipment by primary key."""
        model = self._get_model()
        qs = model._default_manager.filter(pk=shipment_id)
        await sync_to_async(qs.delete)()

    async def find_by_reference(
        self, provider: str, reference_id: str
    ) -> DjangoShipmentAdapter | None:
        """Find a shipment by provider slug and reference_id.

        Returns None if no matching shipment is found.
        """
        model = self._get_model()
        obj = await sync_to_async(
            model._default_manager.filter(
                provider=provider, reference_id=reference_id
            ).first
        )()
        if obj is None:
            return None
        return self._wrap(obj)

    def _unwrap_shipment(self, shipment: Any) -> models.Model:
        """Unwrap a shipment from its adapter if needed."""
        if isinstance(shipment, DjangoShipmentAdapter):
            return shipment.wrapped  # type: ignore[no-any-return]
        return cast(models.Model, shipment)

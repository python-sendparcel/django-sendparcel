"""Django ORM repository for shipment persistence."""

from __future__ import annotations

from typing import Any, cast

import swapper
from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, models
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

    def get_by_id_sync(
        self, shipment_id: str, *, for_update: bool = False
    ) -> DjangoShipmentAdapter:
        """Synchronous fetch a shipment by primary key.

        Used by sync transactional helpers (e.g. webhook callback
        handler) so that ``transaction.atomic()`` works correctly.

        Args:
            shipment_id: Primary key of the shipment.
            for_update: If True, use ``select_for_update()`` to lock
                the row for concurrent-write safety.
        """
        model = self._get_model()
        qs = model._default_manager.filter(pk=shipment_id)
        if for_update:
            qs = qs.select_for_update()
        obj = qs.first()
        if obj is None:
            raise ShipmentNotFoundError(shipment_id)
        return self._wrap(obj)

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
        self,
        shipment_id: str,
        status: str,
        *,
        for_update: bool = True,
        **fields: Any,
    ) -> DjangoShipmentAdapter:
        """Update the status (and optional extra fields) of a shipment.

        Args:
            shipment_id: Primary key of the shipment.
            status: New status value.
            for_update: If True (default), use ``select_for_update()``
                to lock the row for concurrent-write safety.
            **fields: Additional fields to update.

        Returns:
            The updated shipment adapter.
        """
        shipment = await self.get_by_id(shipment_id, for_update=for_update)
        shipment.status = status
        for key, value in fields.items():
            setattr(shipment, key, value)
        model_instance = self._unwrap_shipment(shipment)
        await sync_to_async(model_instance.save)()
        return shipment

    async def update_fields(
        self,
        shipment_id: str,
        **fields: Any,
    ) -> DjangoShipmentAdapter:
        """Atomically update shipment fields by ID.

        Uses Django's ``update()`` queryset method for a single atomic
        SQL UPDATE — no read-modify-save cycle, no race condition.

        Args:
            shipment_id: Primary key of the shipment.
            **fields: Fields to update.

        Returns:
            The updated shipment adapter.

        Raises:
            ShipmentNotFoundError: If no shipment with this ID exists.
        """
        model = self._get_model()
        updated_count = await sync_to_async(
            model._default_manager.filter(pk=shipment_id).update
        )(**fields)
        if updated_count == 0:
            raise ShipmentNotFoundError(shipment_id)
        # Return a fresh adapter for the updated row.
        return await self.get_by_id(shipment_id)

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

    async def create_with_idempotency_key(
        self,
        provider: str,
        status: str,
        reference_id: str,
        **kwargs: Any,
    ) -> tuple[DjangoShipmentAdapter | None, DjangoShipmentAdapter | None]:
        """Atomically check for existing + create if absent.

        Uses a database-level unique constraint on (provider, reference_id)
        to prevent duplicate shipments under concurrent creates.
        Handles the race where two concurrent requests both see "not found"
        and attempt create — the IntegrityError triggers a second lookup
        that returns the record created by the rival request.

        Returns:
            (existing, created) — exactly one is None.
            If a shipment with this provider + reference_id already
            exists, returns (existing, None).
            If no such shipment exists, creates one and returns
            (None, created).
        """
        model = self._get_model()
        try:
            obj = await sync_to_async(
                model._default_manager.get,
            )(provider=provider, reference_id=reference_id)
            return (self._wrap(obj), None)
        except ObjectDoesNotExist:
            try:
                obj = await sync_to_async(model._default_manager.create)(
                    provider=provider,
                    status=status,
                    reference_id=reference_id,
                    **kwargs,
                )
                return (None, self._wrap(obj))
            except IntegrityError:
                # Race: another request created the record between our
                # get() and create().  Do one more lookup to return it.
                obj = await sync_to_async(
                    model._default_manager.get,
                )(provider=provider, reference_id=reference_id)
                return (self._wrap(obj), None)

    def _unwrap_shipment(self, shipment: Any) -> models.Model:
        """Unwrap a shipment from its adapter if needed."""
        if isinstance(shipment, DjangoShipmentAdapter):
            return shipment.wrapped  # type: ignore[no-any-return]
        return cast(models.Model, shipment)

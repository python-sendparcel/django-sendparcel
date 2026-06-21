"""Callback processing pipeline for Django.

Extracts the callback processing logic from views.py into a dedicated
processor. The view becomes a thin HTTP adapter that builds a
CallbackContext and delegates to the processor.
"""
from __future__ import annotations

import json
from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from sendparcel.exceptions import (
    CommunicationError,
    SendParcelException,
)
from sendparcel.flow import ShipmentFlow
from sendparcel.logging import get_logger
from sendparcel.protocols import ShipmentRepository
from sendparcel.types import (
    CallbackContext,
    ShipmentUpdateOutcome,
    ShipmentUpdateResult,
)

from sendparcel_django.conf import get_settings
from sendparcel_django.dedup import DjangoWebhookDedupStore
from sendparcel_django.registry import registry as django_registry

logger = get_logger(__name__)


class CallbackProcessor:
    """Processes webhook callbacks through the core shipment flow.
    
    Owns the transaction boundary, dedup check, and retry storage.
    The view is a thin HTTP adapter that builds a CallbackContext
    and delegates to this processor.
    """
    
    def __init__(
        self,
        repository: ShipmentRepository,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._repository = repository
        self._config = config or {}
    
    async def process(self, ctx: CallbackContext) -> ShipmentUpdateOutcome:
        """Process a callback context through dedup, locking, and provider call."""
        # 1. Dedup check
        dedup_store = DjangoWebhookDedupStore()
        if await dedup_store.is_duplicate(ctx):
            logger.info("Duplicate callback for shipment %s, skipping", ctx.shipment_id)
            raise DuplicateCallbackError(ctx.shipment_id)
        
        # 2. Load locked shipment
        shipment = await sync_to_async(
            self._load_locked,
            thread_sensitive=True,
        )(ctx.shipment_id)
        
        # 3. Call provider (outside transaction)
        flow = ShipmentFlow(
            repository=self._repository,
            config=self._config,
            registry=django_registry,
        )
        outcome = await flow.handle_callback(ctx, shipment=shipment)
        
        # 4. Persist (inside transaction)
        saved = await sync_to_async(
            self._save,
            thread_sensitive=True,
        )(outcome.shipment)
        
        return ShipmentUpdateOutcome(shipment=saved, update=outcome.update)
    
    def _load_locked(self, shipment_id: str) -> Any:
        """Load shipment with select_for_update."""
        with transaction.atomic():
            return self._repository.get_by_id_sync(shipment_id, for_update=True)
    
    def _save(self, shipment: Any) -> Any:
        """Persist shipment inside a transaction."""
        with transaction.atomic():
            shipment.save()
            return shipment


class DuplicateCallbackError(SendParcelException):
    """Raised when a duplicate callback is detected."""
    def __init__(self, shipment_id: str) -> None:
        super().__init__(f"Duplicate callback for shipment {shipment_id}")
        self.shipment_id = shipment_id
"""Callback processing pipeline for Django.

Extracts the callback processing logic from views.py into a dedicated
processor. The view becomes a thin HTTP adapter that builds a
CallbackContext and delegates to the processor.
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync, sync_to_async
from django.db import transaction
from sendparcel.exceptions import SendParcelException
from sendparcel.flow import ShipmentFlow
from sendparcel.logging import get_logger
from sendparcel.protocols import ShipmentRepository
from sendparcel.types import (
    CallbackContext,
    ShipmentUpdateOutcome,
)

from sendparcel_django.dedup import DjangoWebhookDedupStore
from sendparcel_django.registry import registry as django_registry

logger = get_logger(__name__)


class CallbackProcessor:
    """Processes webhook callbacks through the core shipment flow.

    Owns the transaction boundary and the dedup claim. The view is a
    thin HTTP adapter that builds a CallbackContext and delegates to
    this processor.

    The whole pipeline — load with ``select_for_update``, provider
    verify/handle, persist — runs inside a single database
    transaction, so concurrent callbacks for the same shipment are
    serialized at the database level and the FSM transition is
    validated against the locked row. Providers whose callback
    handlers perform network I/O will hold the transaction open for
    the duration of that I/O; keep callback handlers I/O-free where
    possible.
    """

    def __init__(
        self,
        repository: ShipmentRepository,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._repository = repository
        self._config = config or {}

    async def process(self, ctx: CallbackContext) -> ShipmentUpdateOutcome:
        """Process a callback through dedup, locking, and provider."""
        # 1. Dedup claim — inserting first prevents a concurrent
        # identical callback from being processed twice.
        dedup_store = DjangoWebhookDedupStore()
        if await dedup_store.is_duplicate(ctx):
            logger.info(
                "Duplicate callback for shipment %s, skipping",
                ctx.shipment_id,
            )
            raise DuplicateCallbackError(ctx.shipment_id)

        try:
            # 2. Lock, call provider, persist — one transaction.
            outcome = await sync_to_async(
                self._process_locked,
                thread_sensitive=True,
            )(ctx)
        except Exception:
            # Release the claim so a provider redelivery of this
            # payload is processed instead of dropped as a duplicate.
            await dedup_store.release(ctx)
            raise

        return outcome

    def _process_locked(self, ctx: CallbackContext) -> ShipmentUpdateOutcome:
        """Run the callback pipeline inside one locked transaction.

        Runs on the thread-sensitive executor thread. The nested
        ``async_to_sync`` call executes the flow coroutine on the
        outer event loop while repository operations (which use
        ``sync_to_async(thread_sensitive=True)``) hop back to this
        thread — same thread, same connection, same transaction.
        """
        with transaction.atomic():
            shipment = self._repository.get_by_id_sync(
                ctx.shipment_id, for_update=True
            )
            flow = ShipmentFlow(
                repository=self._repository,
                config=self._config,
                registry=django_registry,
            )
            outcome: ShipmentUpdateOutcome = async_to_sync(
                flow.handle_callback
            )(ctx, shipment=shipment)
            return outcome


class DuplicateCallbackError(SendParcelException):
    """Raised when a duplicate callback is detected."""

    def __init__(self, shipment_id: str) -> None:
        super().__init__(f"Duplicate callback for shipment {shipment_id}")
        self.shipment_id = shipment_id

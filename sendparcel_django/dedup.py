"""Webhook deduplication store for django-sendparcel."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta

from asgiref.sync import sync_to_async
from django.db import IntegrityError, OperationalError, connection
from sendparcel.logging import get_logger
from sendparcel.types import CallbackContext

from sendparcel_django.conf import get_settings
from sendparcel_django.models import WebhookDedup

logger = get_logger(__name__)


class DjangoWebhookDedupStore:
    """Django ORM-backed store for webhook deduplication.

    Stores a hash of each webhook payload keyed by shipment_id.
    Duplicates within the configured window are detected via a
    unique constraint on (shipment_id, payload_hash).

    The window is configurable via ``SENDPARCEL_WEBHOOK_DEDUP_WINDOW``
    Django setting (default: 900 seconds = 15 minutes).
    """

    def __init__(self, window_seconds: int | None = None) -> None:
        """Initialize the dedup store.

        Args:
            window_seconds: How long to remember a payload hash before
                considering it stale. Defaults to Django setting
                ``SENDPARCEL_WEBHOOK_DEDUP_WINDOW`` (900s).
        """
        if window_seconds is None:
            window_seconds = get_settings().WEBHOOK_DEDUP_WINDOW
        self.window_seconds = window_seconds

    def _table_exists_sync(self) -> bool:
        """Synchronous check if the WebhookDedup table exists.

        Uses a lightweight SELECT that works across all supported
        backends without needing backend-specific introspection.
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT 1 FROM {WebhookDedup._meta.db_table} LIMIT 0"
                )
            return True
        except OperationalError:
            return False

    async def is_duplicate(
        self,
        ctx: CallbackContext,
        provider_slug: str = "unknown",
    ) -> bool:
        """Check if this payload has been seen recently.

        Uses the ``ctx.dedup_hash`` property for deterministic hashing.

        Attempts to insert a row atomically.  If the unique constraint
        fires (another worker already stored this hash) the record is
        treated as a duplicate.

        If the WebhookDedup table does not exist (e.g. migrations not
        yet applied), dedup is skipped and ``False`` is returned.
        """
        try:
            await sync_to_async(
                WebhookDedup.objects.create,
                thread_sensitive=True,
            )(
                payload_hash=ctx.dedup_hash,
                shipment_id=ctx.shipment_id,
                provider_slug=provider_slug,
            )
        except IntegrityError:
            # Another worker already stored this hash — duplicate.
            return True
        except OperationalError:
            # Table does not exist or other DB error — skip dedup.
            return False

        return False

    async def release(self, ctx: CallbackContext) -> None:
        """Remove the dedup claim for this payload.

        Called when processing fails after the claim was inserted, so
        that a provider redelivery of the identical payload is
        processed instead of being swallowed as a duplicate.
        """
        # Suppress OperationalError: table missing means nothing
        # was claimed in the first place.
        with contextlib.suppress(OperationalError):
            await sync_to_async(
                WebhookDedup.objects.filter(
                    shipment_id=ctx.shipment_id,
                    payload_hash=ctx.dedup_hash,
                ).delete,
                thread_sensitive=True,
            )()

    async def cleanup_old_entries(self) -> int:
        """Remove dedup records older than the window.

        Returns the number of records deleted.
        """
        exists = await sync_to_async(self._table_exists_sync)()
        if not exists:
            return 0

        cutoff = datetime.now(tz=UTC) - timedelta(seconds=self.window_seconds)
        deleted, _ = await sync_to_async(
            lambda: WebhookDedup.objects.filter(created_at__lt=cutoff).delete()
        )()
        return deleted

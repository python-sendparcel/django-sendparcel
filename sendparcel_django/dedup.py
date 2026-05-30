"""Webhook deduplication store for django-sendparcel."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.db import IntegrityError, connection, OperationalError

from sendparcel_django.models import WebhookDedup

logger = logging.getLogger(__name__)


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """Compute a SHA-256 hash of a webhook payload dict.

    The payload is serialised with sorted keys for deterministic hashing
    across different Python versions and dict insertion orders.
    """
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class DjangoWebhookDedupStore:
    """Django ORM-backed store for webhook deduplication.

    Stores a hash of each webhook payload keyed by shipment_id.
    Duplicates within the configured window are detected via a
    unique constraint on (shipment_id, payload_hash).
    """

    def __init__(self, window_seconds: int = 900) -> None:
        """
        Args:
            window_seconds: How long to remember a payload hash
                before considering it stale (default 15 minutes).
        """
        self.window_seconds = window_seconds

    def _table_exists_sync(self) -> bool:
        """Synchronous check if the WebhookDedup table exists."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                [WebhookDedup._meta.db_table],
            )
            return cursor.fetchone() is not None

    async def is_duplicate(
        self,
        payload: dict[str, Any],
        shipment_id: str,
        provider_slug: str = "unknown",
    ) -> bool:
        """Check if this payload has been seen recently.

        Attempts to insert a row atomically.  If the unique constraint
        fires (another worker already stored this hash) the record is
        treated as a duplicate.

        If the WebhookDedup table does not exist (e.g. migrations not
        yet applied), dedup is skipped and ``False`` is returned.
        """
        payload_hash = compute_payload_hash(payload)

        try:
            await sync_to_async(
                WebhookDedup.objects.create,
                thread_sensitive=True,
            )(
                payload_hash=payload_hash,
                shipment_id=shipment_id,
                provider_slug=provider_slug,
            )
        except IntegrityError:
            # Another worker already stored this hash — duplicate.
            return True
        except OperationalError:
            # Table does not exist or other DB error — skip dedup.
            return False

        return False

    async def cleanup_old_entries(self) -> int:
        """Remove dedup records older than the window.

        Returns the number of records deleted.
        """
        exists = await sync_to_async(self._table_exists_sync)()
        if not exists:
            return 0

        cutoff = datetime.now(tz=UTC) - timedelta(seconds=self.window_seconds)
        deleted, _ = await sync_to_async(
            lambda: WebhookDedup.objects.filter(
                created_at__lt=cutoff
            ).delete()
        )()
        return deleted

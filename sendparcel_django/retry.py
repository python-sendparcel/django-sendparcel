"""Callback retry mechanism for django-sendparcel."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.db.models import Q
from sendparcel.logging import get_logger

from sendparcel_django.conf import get_settings
from sendparcel_django.models import CallbackRetry

logger = get_logger(__name__)


def compute_next_retry_at(
    attempt: int,
    backoff_seconds: int | None = None,
    jitter_fraction: float = 0.1,
) -> datetime:
    """Compute next retry time using exponential backoff with jitter.

    delay = backoff_seconds * 2^(attempt - 1) * (1 ± jitter)

    Jitter prevents thundering herd when many retries are scheduled
    for the same time after a provider outage.

    Args:
        attempt: Current attempt number (1-based).
        backoff_seconds: Base delay in seconds. Defaults to Django setting.
        jitter_fraction: Fraction of delay to randomize (0.0-1.0).
            Default 0.1 = +/-10% jitter.
    """
    if backoff_seconds is None:
        backoff_seconds = get_settings().CALLBACK_RETRY_BACKOFF_BASE

    base_delay = backoff_seconds * (2 ** (attempt - 1))
    # Apply jitter: randomize between (1 - jitter) and (1 + jitter)
    jitter = base_delay * jitter_fraction
    delay = base_delay + random.uniform(-jitter, jitter)
    return datetime.now(tz=UTC) + timedelta(seconds=max(0, delay))


class DjangoCallbackRetryStore:
    """Django ORM-backed store for callback retry records."""

    async def store_failed_callback(
        self,
        shipment_id: str,
        provider_slug: str,
        payload: dict[str, Any],
        headers: dict[str, Any],
        source_ip: str = "",
        raw_body: bytes = b"",
    ) -> str:
        """Persist a failed callback for later retry.

        Returns the retry record ID as a string.
        """
        record = await sync_to_async(CallbackRetry.objects.create)(
            shipment_id=shipment_id,
            provider_slug=provider_slug,
            payload=payload,
            headers=headers,
            source_ip=source_ip or None,
            raw_body=raw_body or None,
        )
        return str(record.id)

    async def get_due_retries(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return pending retries that are due for processing.

        Records with null next_retry_at are considered immediately due.
        """
        now = datetime.now(tz=UTC)
        qs_queryset = (
            CallbackRetry.objects.filter(status="pending")
            .filter(
                Q(next_retry_at__lte=now) | Q(next_retry_at__isnull=True),
            )
            .order_by("created_at")[:limit]
        )
        qs: list[CallbackRetry] = await sync_to_async(
            lambda: list(qs_queryset)
        )()

        return [
            {
                "id": str(record.id),
                "shipment_id": record.shipment_id,
                "payload": record.payload,
                "headers": record.headers,
                "source_ip": record.source_ip,
                "raw_body": record.raw_body,
                "attempts": record.attempts,
            }
            for record in qs
        ]

    async def mark_succeeded(self, retry_id: str) -> None:
        """Mark a retry record as successfully processed."""
        await sync_to_async(
            CallbackRetry.objects.filter(id=retry_id).update,
        )(status="succeeded")

    async def mark_failed(
        self,
        retry_id: str,
        error: str,
        backoff_seconds: int = 60,
    ) -> None:
        """Increment attempts, record error, schedule next retry."""
        record = await sync_to_async(
            CallbackRetry.objects.get,
        )(id=retry_id)
        record.attempts += 1
        record.last_error = error
        record.next_retry_at = compute_next_retry_at(
            attempt=record.attempts,
            backoff_seconds=backoff_seconds,
        )
        await sync_to_async(record.save)(
            update_fields=[
                "attempts",
                "last_error",
                "next_retry_at",
            ],
        )

    async def mark_exhausted(self, retry_id: str) -> None:
        """Mark a retry record as exhausted (no more retries)."""
        await sync_to_async(
            CallbackRetry.objects.filter(id=retry_id).update,
        )(status="exhausted")


async def _process_single_retry(
    flow: Any, repository: Any, retry_record: dict[str, Any]
) -> None:
    """Process a single retry record asynchronously."""
    from sendparcel.types import CallbackContext

    shipment = await repository.get_by_id(retry_record["shipment_id"])
    ctx = CallbackContext(
        shipment_id=retry_record["shipment_id"],
        payload=retry_record["payload"],
        headers=retry_record["headers"],
        source_ip=retry_record.get("source_ip", ""),
        raw_body=retry_record.get("raw_body", b""),
    )
    await flow.handle_callback(ctx, shipment=shipment)


async def process_due_retries(
    *,
    retry_store: DjangoCallbackRetryStore,
    flow: Any,
    repository: Any,
    max_attempts: int = 5,
    backoff_seconds: int = 60,
    limit: int = 10,
) -> int:
    """Process pending callback retries.

    Returns the number of successfully processed retries.
    """
    due = await retry_store.get_due_retries(limit=limit)
    succeeded = 0

    for retry_record in due:
        retry_id = retry_record["id"]
        current_attempts = retry_record["attempts"]

        if current_attempts >= max_attempts:
            logger.warning(
                "Retry exhausted for shipment %s after %d attempts",
                retry_record["shipment_id"],
                current_attempts,
            )
            await retry_store.mark_exhausted(retry_id)
            continue

        try:
            await _process_single_retry(flow, repository, retry_record)
            await retry_store.mark_succeeded(retry_id)
            succeeded += 1
        except Exception as exc:
            new_attempts = current_attempts + 1
            if new_attempts >= max_attempts:
                logger.warning(
                    "Retry exhausted for shipment %s after %d attempts: %s",
                    retry_record["shipment_id"],
                    new_attempts,
                    exc,
                )
                await retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                    backoff_seconds=backoff_seconds,
                )
                await retry_store.mark_exhausted(retry_id)
            else:
                await retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                    backoff_seconds=backoff_seconds,
                )

    return succeeded

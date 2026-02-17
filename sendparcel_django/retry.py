"""Callback retry mechanism for django-sendparcel."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import anyio
from django.db.models import Q

from sendparcel_django.models import CallbackRetry


def compute_next_retry_at(
    attempt: int,
    backoff_seconds: int = 60,
) -> datetime:
    """Compute next retry time using exponential backoff.

    delay = backoff_seconds * 2^(attempt - 1)
    """
    delay = backoff_seconds * (2 ** (attempt - 1))
    return datetime.now(tz=UTC) + timedelta(seconds=delay)


class DjangoCallbackRetryStore:
    """Django ORM-backed store for callback retry records."""

    def store_failed_callback(
        self,
        shipment_id: str,
        provider_slug: str,
        payload: dict,
        headers: dict,
    ) -> str:
        """Persist a failed callback for later retry.

        Returns the retry record ID as a string.
        """
        record = CallbackRetry.objects.create(
            shipment_id=shipment_id,
            provider_slug=provider_slug,
            payload=payload,
            headers=headers,
        )
        return str(record.id)

    def get_due_retries(self, limit: int = 10) -> list[dict]:
        """Return pending retries that are due for processing.

        Records with null next_retry_at are considered immediately due.
        """
        now = datetime.now(tz=UTC)
        qs = (
            CallbackRetry.objects.filter(status="pending")
            .filter(
                Q(next_retry_at__lte=now) | Q(next_retry_at__isnull=True),
            )
            .order_by("created_at")[:limit]
        )

        return [
            {
                "id": str(record.id),
                "shipment_id": record.shipment_id,
                "payload": record.payload,
                "headers": record.headers,
                "attempts": record.attempts,
            }
            for record in qs
        ]

    def mark_succeeded(self, retry_id: str) -> None:
        """Mark a retry record as successfully processed."""
        CallbackRetry.objects.filter(id=retry_id).update(
            status="succeeded",
        )

    def mark_failed(
        self,
        retry_id: str,
        error: str,
        backoff_seconds: int = 60,
    ) -> None:
        """Increment attempts, record error, schedule next retry."""
        record = CallbackRetry.objects.get(id=retry_id)
        record.attempts += 1
        record.last_error = error
        record.next_retry_at = compute_next_retry_at(
            attempt=record.attempts,
            backoff_seconds=backoff_seconds,
        )
        record.save(
            update_fields=[
                "attempts",
                "last_error",
                "next_retry_at",
            ],
        )

    def mark_exhausted(self, retry_id: str) -> None:
        """Mark a retry record as exhausted (no more retries)."""
        CallbackRetry.objects.filter(id=retry_id).update(
            status="exhausted",
        )


async def _process_single_retry(flow, repository, retry_record: dict):
    """Process a single retry record asynchronously."""
    shipment = await repository.get_by_id(retry_record["shipment_id"])
    await flow.handle_callback(
        shipment,
        retry_record["payload"],
        retry_record["headers"],
    )


def process_due_retries(
    *,
    retry_store: DjangoCallbackRetryStore,
    flow,
    repository,
    max_attempts: int = 5,
    backoff_seconds: int = 60,
    limit: int = 10,
) -> int:
    """Process pending callback retries.

    Returns the number of successfully processed retries.
    """
    due = retry_store.get_due_retries(limit=limit)
    succeeded = 0

    for retry_record in due:
        retry_id = retry_record["id"]
        current_attempts = retry_record["attempts"]

        if current_attempts >= max_attempts:
            retry_store.mark_exhausted(retry_id)
            continue

        try:
            anyio.run(
                _process_single_retry,
                flow,
                repository,
                retry_record,
            )
            retry_store.mark_succeeded(retry_id)
            succeeded += 1
        except Exception as exc:
            new_attempts = current_attempts + 1
            if new_attempts >= max_attempts:
                retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                    backoff_seconds=backoff_seconds,
                )
                retry_store.mark_exhausted(retry_id)
            else:
                retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                    backoff_seconds=backoff_seconds,
                )

    return succeeded

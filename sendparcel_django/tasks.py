"""Background tasks for django-sendparcel.

Replaces the legacy Celery integration with ``django-tasks`` for
background processing of callback retries, dedup cleanup, and
shipment status polling.

To use, configure the task backend in your Django settings::

    TASKS = {
        "default": {
            "BACKEND": "django_tasks.backends.immediate.ImmediateBackend",
        }
    }

For production with async workers, use a backend that supports
asynchronous execution (e.g. a database-backed backend with
``django-tasks-postgres`` or similar).

Tasks are imported automatically when ``sendparcel_django`` is in
``INSTALLED_APPS``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import swapper
from asgiref.sync import sync_to_async
from django_tasks import task
from sendparcel.enums import ShipmentStatus
from sendparcel.flow import ShipmentFlow
from sendparcel.logging import get_logger

from sendparcel_django.dedup import DjangoWebhookDedupStore
from sendparcel_django.registry import registry
from sendparcel_django.repository import DjangoShipmentRepository
from sendparcel_django.retry import (
    DjangoCallbackRetryStore,
    process_due_retries,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Shared async helpers (no anyio.run — runs in the task's event loop)
# ---------------------------------------------------------------------------


def _ensure_registry_discovered() -> None:
    """Ensure provider registry is populated (idempotent)."""
    registry.discover()


def _get_provider_config() -> dict[str, Any]:
    """Load provider settings from Django settings."""
    from django.conf import settings

    return cast(
        dict[str, Any],
        getattr(settings, "SENDPARCEL_PROVIDER_SETTINGS", {}),
    )


async def _poll_single_shipment_status(
    shipment_id: str,
    provider_slug: str,
    *,
    max_retries: int = 3,
    poll_interval: int = 60,
) -> dict[str, Any] | None:
    """Poll a single shipment's status via ``ShipmentFlow``.

    Uses the flow's ``fetch_and_update_status`` method so that updates
    are persisted atomically through the repository.

    Args:
        shipment_id: The Django shipment ID.
        provider_slug: The provider slug (e.g. ``"inpost_courier"``).
        max_retries: Number of times to retry on transient failure.
        poll_interval: Seconds between polls (used for backoff).

    Returns:
        The status update dict if successful, or ``None`` on failure.
    """
    _ensure_registry_discovered()

    repository = DjangoShipmentRepository()
    shipment = await repository.get_by_id(shipment_id)
    if shipment is None:
        logger.warning("Shipment %s not found for polling", shipment_id)
        return None

    provider_config = _get_provider_config()
    flow = ShipmentFlow(
        repository=repository,
        config=provider_config,
        registry=registry,
    )

    for attempt in range(1, max_retries + 1):
        try:
            outcome = await flow.fetch_and_update_status(shipment)
            logger.info(
                "Poll result for shipment %s (attempt %d): %s",
                shipment_id,
                attempt,
                outcome.update,
            )
            return cast(dict[str, Any], outcome.update)
        except Exception as exc:
            if attempt == max_retries:
                logger.error(
                    "Poll failed for shipment %s after %d attempts: %s",
                    shipment_id,
                    max_retries,
                    exc,
                )
                return None
            wait = poll_interval * (2 ** (attempt - 1))
            logger.warning(
                "Poll attempt %d failed for shipment %s, retrying in %ds: %s",
                attempt,
                shipment_id,
                wait,
                exc,
            )
            import asyncio

            await asyncio.sleep(wait)

    return None


# ---------------------------------------------------------------------------
# django-tasks — async background tasks (no Celery, no anyio.run)
# ---------------------------------------------------------------------------


@task(
    priority=1,
)
async def process_due_retries_task(
    *,
    limit: int = 10,
    max_attempts: int = 5,
    backoff_seconds: int = 60,
) -> dict[str, Any]:
    """Process pending callback retries.

    Delegates to :func:`process_due_retries` for actual processing.

    Args:
        limit: Maximum retries to process per run.
        max_attempts: Max attempts before marking as exhausted.
        backoff_seconds: Base backoff for exponential retry.

    Returns:
        Dict with ``processed`` count and ``timestamp``.
    """
    try:
        count = await process_due_retries(
            retry_store=DjangoCallbackRetryStore(),
            flow=ShipmentFlow(
                repository=DjangoShipmentRepository(),
            ),
            repository=DjangoShipmentRepository(),
            max_attempts=max_attempts,
            backoff_seconds=backoff_seconds,
            limit=limit,
        )

        logger.info("Task processed %d retry record(s).", count)

        return {
            "processed": count,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
    except Exception as exc:
        logger.error("Task process_due_retries failed: %s", exc)
        raise


@task(
    priority=2,
)
async def cleanup_dedup_task(
    *,
    window: int = 900,
) -> dict[str, Any]:
    """Clean up old webhook dedup records.

    Args:
        window: Age in seconds after which records are considered stale.

    Returns:
        Dict with ``deleted`` count and ``timestamp``.
    """
    try:
        store = DjangoWebhookDedupStore(window_seconds=window)
        deleted = await store.cleanup_old_entries()

        logger.info("Task cleaned up %d dedup record(s).", deleted)

        return {
            "deleted": deleted,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
    except Exception as exc:
        logger.error("Task cleanup_dedup failed: %s", exc)
        raise


@task(
    priority=1,
)
async def poll_shipment_status_task(
    shipment_id: str,
    provider_slug: str,
    *,
    max_retries: int = 3,
    poll_interval: int = 60,
) -> dict[str, Any]:
    """Poll a single shipment's status from its provider.

    Args:
        shipment_id: The Django shipment ID to poll.
        provider_slug: The provider slug (e.g. ``"inpost_courier"``).
        max_retries: Number of retry attempts on transient failure.
        poll_interval: Base interval in seconds between polls.

    Returns:
        Dict with ``status`` (``"updated"`` or ``"failed"``),
        ``shipment_id``, and optional ``result`` or ``error``.
    """
    try:
        result = await _poll_single_shipment_status(
            shipment_id,
            provider_slug,
            max_retries=max_retries,
            poll_interval=poll_interval,
        )

        if result is not None:
            logger.info(
                "Poll completed for shipment %s: %s",
                shipment_id,
                result,
            )
            return {
                "status": "updated",
                "shipment_id": shipment_id,
                "result": result,
            }
        else:
            logger.warning(
                "Poll returned no result for shipment %s",
                shipment_id,
            )
            return {
                "status": "failed",
                "shipment_id": shipment_id,
                "error": "No result from provider",
            }
    except Exception as exc:
        logger.error(
            "Task poll_shipment_status failed for %s: %s",
            shipment_id,
            exc,
        )
        raise


@task(
    priority=1,
)
async def poll_all_pending_statuses_task(
    *,
    limit: int = 50,
    max_retries: int = 3,
    poll_interval: int = 60,
) -> dict[str, Any]:
    """Poll all shipments with pending statuses.

    Fetches shipments with status ``"label_ready"`` or ``"in_transit"``
    and polls each one for an updated status.

    Args:
        limit: Maximum shipments to poll per run.
        max_retries: Retries per shipment.
        poll_interval: Base poll interval in seconds.

    Returns:
        Dict with ``polled``, ``updated``, ``failed`` counts.
    """
    try:
        _ensure_registry_discovered()

        pending_statuses = [
            ShipmentStatus.LABEL_READY.value,
            ShipmentStatus.IN_TRANSIT.value,
        ]

        model = swapper.load_model("sendparcel_django", "Shipment")
        shipments = await sync_to_async(
            lambda: list(
                model._default_manager.filter(status__in=pending_statuses)
                .order_by("created_at")[:limit]
                .values_list("pk", "provider")
            )
        )()

        if not shipments:
            logger.info("No pending shipments to poll.")
            return {
                "polled": 0,
                "updated": 0,
                "failed": 0,
                "timestamp": datetime.now(tz=UTC).isoformat(),
            }

        updated = 0
        failed = 0

        for shipment_id, provider_slug in shipments:
            result = await _poll_single_shipment_status(
                shipment_id,
                provider_slug,
                max_retries=max_retries,
                poll_interval=poll_interval,
            )
            if result is not None:
                updated += 1
            else:
                failed += 1

        logger.info(
            "Poll batch: %d polled, %d updated, %d failed.",
            len(shipments),
            updated,
            failed,
        )

        return {
            "polled": len(shipments),
            "updated": updated,
            "failed": failed,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
    except Exception as exc:
        logger.error("Task poll_all_pending_statuses failed: %s", exc)
        raise

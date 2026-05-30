"""Celery application and tasks for django-sendparcel.

This module provides Celery integration for background processing of
callback retries, dedup cleanup, and shipment status polling.

To use, configure Celery in your Django settings::

    CELERY_BROKER_URL = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND = "redis://localhost:6379/0"

And add ``sendparcel_django.celery`` to ``INSTALLED_APPS`` or configure
the ``CELERY_BROKER_URL`` setting to auto-discover tasks.
"""

from __future__ import annotations

import anyio
from datetime import UTC, datetime
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from sendparcel.flow import ShipmentFlow
from sendparcel.logging import get_logger
from sendparcel_django.repository import DjangoShipmentRepository

from sendparcel_django.dedup import DjangoWebhookDedupStore
from sendparcel_django.models import CallbackRetry
from sendparcel_django.registry import registry
from sendparcel_django.retry import DjangoCallbackRetryStore, process_due_retries

logger = get_logger(__name__)

# Lazy Celery app — only imported when Celery is available.
try:
    from celery import Celery

    app = Celery("sendparcel")
    app.config_from_object("django.conf:settings", namespace="CELERY")
    app.autodiscover_tasks()
except ImportError:
    app = None  # type: ignore[assignment]


def _get_celery_app() -> Celery:
    """Return the Celery app, raising if Celery is not installed."""
    if app is None:
        raise RuntimeError(
            "Celery is not installed. "
            "Install it with: pip install celery"
        )
    return app  # type: ignore[return-value]


def _ensure_registry_discovered() -> None:
    """Ensure provider registry is populated (idempotent)."""
    registry.discover()


def _poll_single_shipment_status_sync(
    shipment_id: str,
    provider_slug: str,
    *,
    max_retries: int = 3,
    poll_interval: int = 60,
) -> dict[str, Any] | None:
    """Synchronous wrapper for polling a single shipment's status.

    Uses ``anyio.run`` to execute the async polling logic.

    Args:
        shipment_id: The Django shipment ID.
        provider_slug: The provider slug (e.g. ``"inpost_courier"``).
        max_retries: Number of times to retry on transient failure.
        poll_interval: Seconds between polls (used for backoff).

    Returns:
        The status update dict if successful, or ``None`` on failure.
    """
    import asyncio

    async def _poll() -> dict[str, Any] | None:
        _ensure_registry_discovered()

        repository = DjangoShipmentRepository()
        flow = ShipmentFlow()

        shipment = await repository.get_by_id(shipment_id)
        if shipment is None:
            logger.warning("Shipment %s not found for polling", shipment_id)
            return None

        provider = registry.get(provider_slug)
        if provider is None:
            logger.error("Provider %s not registered for polling", provider_slug)
            return None

        for attempt in range(1, max_retries + 1):
            try:
                result = await provider.fetch_shipment_status(shipment)
                logger.info(
                    "Poll result for shipment %s (attempt %d): %s",
                    shipment_id,
                    attempt,
                    result,
                )
                return result
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
                await asyncio.sleep(wait)

        return None

    return anyio.run(_poll)


# ---------------------------------------------------------------------------
# Celery tasks — only defined when Celery is installed
# ---------------------------------------------------------------------------

if app is not None:

    @app.task(
        name="sendparcel.process_due_retries",
        bind=True,
        max_retries=3,
        default_retry_delay=60,
    )
    def process_due_retries_task(
        self,
        *,
        limit: int = 10,
        max_attempts: int = 5,
        backoff_seconds: int = 60,
    ) -> dict[str, Any]:
        """Celery task to process pending callback retries.

        Delegates to :func:`process_due_retries` for actual processing.

        Args:
            limit: Maximum retries to process per run.
            max_attempts: Max attempts before marking as exhausted.
            backoff_seconds: Base backoff for exponential retry.

        Returns:
            Dict with ``processed`` count and ``timestamp``.
        """
        try:
            count = anyio.run(
                process_due_retries,
                retry_store=DjangoCallbackRetryStore(),
                flow=ShipmentFlow(),
                repository=DjangoShipmentRepository(),
                max_attempts=max_attempts,
                backoff_seconds=backoff_seconds,
                limit=limit,
            )

            logger.info(
                "Celery task processed %d retry record(s).", count,
            )

            return {
                "processed": count,
                "timestamp": datetime.now(tz=UTC).isoformat(),
            }
        except Exception as exc:
            logger.error("Celery task process_due_retries failed: %s", exc)
            raise self.retry(exc=exc) from exc

    @app.task(
        name="sendparcel.cleanup_dedup",
        bind=True,
        max_retries=2,
        default_retry_delay=30,
    )
    def cleanup_dedup_task(
        *,
        window: int = 900,
    ) -> dict[str, Any]:
        """Celery task to clean up old webhook dedup records.

        Args:
            window: Age in seconds after which records are considered stale.

        Returns:
            Dict with ``deleted`` count and ``timestamp``.
        """
        try:
            store = DjangoWebhookDedupStore(window_seconds=window)
            deleted = anyio.run(store.cleanup_old_entries)

            logger.info(
                "Celery task cleaned up %d dedup record(s).", deleted,
            )

            return {
                "deleted": deleted,
                "timestamp": datetime.now(tz=UTC).isoformat(),
            }
        except Exception as exc:
            logger.error("Celery task cleanup_dedup failed: %s", exc)
            raise self.retry(exc=exc) from exc

    @app.task(
        name="sendparcel.poll_shipment_status",
        bind=True,
        max_retries=3,
        default_retry_delay=60,
    )
    def poll_shipment_status_task(
        self,
        shipment_id: str,
        provider_slug: str,
        *,
        max_retries: int = 3,
        poll_interval: int = 60,
    ) -> dict[str, Any]:
        """Celery task to poll a single shipment's status from its provider.

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
            result = _poll_single_shipment_status_sync(
                shipment_id,
                provider_slug,
                max_retries=max_retries,
                poll_interval=poll_interval,
            )

            if result is not None:
                logger.info(
                    "Poll completed for shipment %s: %s", shipment_id, result,
                )
                return {
                    "status": "updated",
                    "shipment_id": shipment_id,
                    "result": result,
                }
            else:
                logger.warning(
                    "Poll returned no result for shipment %s", shipment_id,
                )
                return {
                    "status": "failed",
                    "shipment_id": shipment_id,
                    "error": "No result from provider",
                }
        except Exception as exc:
            logger.error(
                "Celery task poll_shipment_status failed for %s: %s",
                shipment_id,
                exc,
            )
            raise self.retry(exc=exc) from exc

    @app.task(
        name="sendparcel.poll_all_pending_statuses",
        bind=True,
        max_retries=2,
        default_retry_delay=60,
    )
    def poll_all_pending_statuses_task(
        self,
        *,
        limit: int = 50,
        max_retries: int = 3,
        poll_interval: int = 60,
    ) -> dict[str, Any]:
        """Celery task to poll all pending shipment statuses.

        Fetches shipments with status ``"label_ready"`` or ``"in_transit"``
        that haven't been polled recently and polls each one.

        Args:
            limit: Maximum shipments to poll per run.
            max_retries: Retries per shipment.
            poll_interval: Base poll interval in seconds.

        Returns:
            Dict with ``polled``, ``updated``, ``failed`` counts.
        """
        import asyncio

        async def _poll_batch() -> dict[str, Any]:
            from sendparcel.enums import ShipmentStatus

            _ensure_registry_discovered()

            pending_statuses = [
                ShipmentStatus.LABEL_READY.value,
                ShipmentStatus.IN_TRANSIT.value,
            ]

            shipments = await sync_to_async(
                lambda: list(
                    CallbackRetry.objects.filter(
                        status__in=pending_statuses
                    )
                    .order_by("created_at")[:limit]
                    .values_list("shipment_id", "provider_slug")
                    .distinct()
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
                result = _poll_single_shipment_status_sync(
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

        try:
            return anyio.run(_poll_batch)
        except Exception as exc:
            logger.error(
                "Celery task poll_all_pending_statuses failed: %s", exc,
            )
            raise self.retry(exc=exc) from exc

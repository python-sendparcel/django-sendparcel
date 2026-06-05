"""Django views for callback endpoints."""

from __future__ import annotations

import json
from typing import Any, cast

from asgiref.sync import sync_to_async
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    ProviderCapabilityError,
    ProviderNotFoundError,
    SendParcelException,
    ShipmentNotFoundError,
)
from sendparcel.flow import ShipmentFlow
from sendparcel.logging import get_logger
from sendparcel.protocols import ShipmentRepository
from sendparcel.types import ShipmentUpdateOutcome, ShipmentUpdateResult

from sendparcel_django.conf import get_settings
from sendparcel_django.dedup import DjangoWebhookDedupStore
from sendparcel_django.registry import registry as django_registry

logger = get_logger(__name__)


def _check_content_type(request: HttpRequest) -> JsonResponse | None:
    """Validate webhook content-type.

    Returns a 415 response if the content-type is wrong, or None to
    proceed with processing.
    """
    allowed = get_settings().WEBHOOK_CONTENT_TYPE
    content_type = request.content_type or ""
    # Allow exact match or media type with params
    if not content_type.startswith(allowed):
        return JsonResponse(
            {"detail": f"Content-Type must be {allowed}"},
            status=415,
        )
    return None


def _check_payload_size(request: HttpRequest) -> JsonResponse | None:
    """Validate webhook payload size."""
    max_size = get_settings().WEBHOOK_MAX_PAYLOAD_SIZE
    if len(request.body) > max_size:
        return JsonResponse(
            {"detail": f"Payload too large (max {max_size} bytes)"},
            status=413,
        )
    return None


@csrf_exempt
@require_POST
async def callback(
    request: HttpRequest,
    shipment_id: str,
    *,
    repository: ShipmentRepository | None = None,
    config: dict[str, Any] | None = None,
) -> JsonResponse:
    """Handle provider callbacks through the core shipment flow.

    The callback path is wrapped in a DB transaction with row-level
    locking (``select_for_update``) to ensure atomicity under
    concurrency — simultaneous callbacks for the same shipment are
    serialized at the database level.

    Async view for Django 5.2+ ASGI. Shares the server's event loop
    instead of spawning a new one per request (which ``anyio.run()`` did).

    Security:
        - Content-Type validation (default: application/json)
        - Payload size limit (default: 64 KB)
        - Source IP verification delegated to provider
    """
    # Validate content-type early
    ct_response = _check_content_type(request)
    if ct_response is not None:
        return ct_response

    # Validate payload size early
    size_response = _check_payload_size(request)
    if size_response is not None:
        return size_response

    if repository is None:
        from sendparcel_django.repository import DjangoShipmentRepository

        repository = cast(ShipmentRepository, DjangoShipmentRepository())

    try:
        payload = (
            cast(dict[str, Any], json.loads(request.body.decode("utf-8")))
            if getattr(request, "body", b"")
            else {}
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"detail": "Invalid JSON payload.", "code": "invalid_json"},
            status=400,
        )

    # Deduplication check: skip processing if this payload was already
    # handled within the configured window.  Returns 200 OK immediately
    # so the provider does not retry.
    dedup_store = DjangoWebhookDedupStore()
    if await dedup_store.is_duplicate(payload, shipment_id):
        logger.info("Duplicate webhook for shipment %s, skipping", shipment_id)
        return JsonResponse({"status": "accepted"}, status=200)

    # Validate source IP from the actual TCP connection, not from spoofable
    # headers. Pass the validated IP directly to the provider.
    source_ip = request.META.get("REMOTE_ADDR", "")
    headers: dict[str, str] = dict(getattr(request, "headers", {}))

    flow = ShipmentFlow(
        repository=repository,
        config=config or {},
        registry=django_registry,
    )

    try:
        outcome = await _handle_callback(
            flow,
            repository,
            shipment_id,
            payload,
            headers,
            getattr(request, "body", b""),
            source_ip=source_ip,
        )
    except CommunicationError as exc:
        # Store for later retry so transient failures are recovered.
        await _store_failed_callback_for_retry(
            shipment_id=shipment_id,
            payload=payload,
            headers=dict(headers),
            source_ip=source_ip,
            raw_body=getattr(request, "body", b""),
            exc=exc,
        )
        return JsonResponse(
            {"detail": str(exc), "code": "communication_error"},
            status=502,
        )
    except InvalidTransitionError as exc:
        return JsonResponse(
            {"detail": str(exc), "code": "invalid_transition"},
            status=409,
        )
    except InvalidCallbackError as exc:
        return JsonResponse(
            {"detail": str(exc), "code": "invalid_callback"},
            status=400,
        )
    except ShipmentNotFoundError as exc:
        return JsonResponse(
            {"detail": str(exc), "code": "shipment_not_found"},
            status=404,
        )
    except ProviderNotFoundError as exc:
        return JsonResponse(
            {"detail": str(exc), "code": "provider_not_found"},
            status=404,
        )
    except ProviderCapabilityError as exc:
        return JsonResponse(
            {"detail": str(exc), "code": "provider_capability_error"},
            status=409,
        )
    except SendParcelException as exc:
        return JsonResponse(
            {"detail": str(exc), "code": "sendparcel_error"},
            status=400,
        )

    return JsonResponse(
        {
            "provider": str(outcome.shipment.provider),
            "status": "accepted",
            "shipment": _serialize_shipment(outcome.shipment),
            "update": _serialize_update(outcome.update),
        }
    )


def _load_shipment_locked(
    repository: ShipmentRepository, shipment_id: str
) -> Any:
    """Load a shipment with ``select_for_update`` inside a transaction.

    Returns the shipment object.  The caller is responsible for applying
    changes back through the repository inside its own ``atomic()`` block.
    """
    with transaction.atomic():
        return repository.get_by_id_sync(shipment_id, for_update=True)


def _save_shipment_sync(shipment: Any) -> Any:
    """Persist a shipment inside a sync transaction boundary."""
    with transaction.atomic():
        shipment.save()
        return shipment


async def _handle_callback(
    flow: ShipmentFlow,
    repository: ShipmentRepository,
    shipment_id: str,
    payload: dict[str, Any],
    headers: dict[str, Any],
    raw_body: bytes,
    **kwargs: Any,
) -> ShipmentUpdateOutcome:
    """Handle a callback with DB transaction and row-level locking.

    The ``select_for_update`` lock serialises concurrent callbacks for
    the same shipment.  Async provider calls (HTTP) happen outside the
    transaction; only ORM reads/writes live inside it.
    """
    # 1. Load locked shipment inside a transaction boundary.
    shipment = await sync_to_async(
        _load_shipment_locked,
        thread_sensitive=True,
    )(repository, shipment_id)

    # 2. Call async providers outside the transaction.
    outcome = await flow.handle_callback(
        shipment,
        payload,
        headers,
        raw_body=raw_body,
        **kwargs,
    )

    # 3. Persist the result inside a sync transaction boundary.
    saved = await sync_to_async(
        _save_shipment_sync,
        thread_sensitive=True,
    )(outcome.shipment)
    return ShipmentUpdateOutcome(shipment=saved, update=outcome.update)


def _serialize_shipment(shipment: Any) -> dict[str, str]:
    return {
        "id": str(shipment.id),
        "status": str(shipment.status),
        "provider": str(shipment.provider),
        "external_id": str(shipment.external_id),
        "tracking_number": str(shipment.tracking_number),
    }


def _serialize_update(update: ShipmentUpdateResult) -> dict[str, Any]:
    return {
        "status": (
            str(update.get("status"))
            if update.get("status") is not None
            else None
        ),
        "tracking_number": (
            str(update.get("tracking_number"))
            if update.get("tracking_number") is not None
            else None
        ),
        "tracking_events": list(update.get("tracking_events", [])),
    }


async def _store_failed_callback_for_retry(
    *,
    shipment_id: str,
    payload: dict[str, Any],
    headers: dict[str, Any],
    source_ip: str,
    raw_body: bytes,
    exc: CommunicationError,
) -> None:
    """Persist a failed callback for later retry processing.

    The provider_slug is set to ``"unknown"`` here because the
    error may have occurred before the shipment was fully loaded.
    The retry processor resolves the provider from the database
    shipment record at retry time.
    """
    from sendparcel_django.retry import DjangoCallbackRetryStore

    retry_store = DjangoCallbackRetryStore()
    try:
        retry_id = await retry_store.store_failed_callback(
            shipment_id=shipment_id,
            provider_slug="unknown",
            payload=payload,
            headers=headers,
            source_ip=source_ip,
            raw_body=raw_body,
        )
        logger.info(
            "Stored failed callback for retry (id=%s, shipment=%s, error=%s)",
            retry_id,
            shipment_id,
            exc,
        )
    except Exception as store_exc:
        logger.error(
            "Failed to store callback retry for shipment %s: %s",
            shipment_id,
            store_exc,
        )

"""Django views for callback endpoints."""

from __future__ import annotations

import json
from typing import Any, cast

from asgiref.sync import sync_to_async
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from sendparcel.enums import ShipmentStatus
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

from sendparcel_django.dedup import DjangoWebhookDedupStore
from sendparcel_django.registry import registry as django_registry

logger = get_logger(__name__)

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

    Async view for Django 5.2+ ASGI. Shares the server's event loop
    instead of spawning a new one per request (which ``anyio.run()`` did).
    """
    if repository is None:
        from sendparcel_django.repository import DjangoShipmentRepository

        repository = DjangoShipmentRepository()

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


async def _handle_callback(
    flow: ShipmentFlow,
    repository: ShipmentRepository,
    shipment_id: str,
    payload: dict[str, Any],
    headers: dict[str, Any],
    raw_body: bytes,
    **kwargs: Any,
) -> ShipmentUpdateOutcome:
    shipment = await repository.get_by_id(shipment_id)
    return await flow.handle_callback(
        shipment,
        payload,
        headers,
        raw_body=raw_body,
        **kwargs,
    )


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

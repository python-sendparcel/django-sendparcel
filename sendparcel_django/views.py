"""Django views for callback endpoints."""

from __future__ import annotations

import json
from typing import Any, cast

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from sendparcel.exceptions import (
    CommunicationError,
    SendParcelException,
)
from sendparcel.logging import get_logger
from sendparcel.protocols import ShipmentRepository
from sendparcel.types import CallbackContext

from sendparcel_django.callback import CallbackProcessor, DuplicateCallbackError
from sendparcel_django.conf import get_settings
from sendparcel_django.ip_resolution import resolve_client_ip
from sendparcel_django.middleware import _exception_to_response

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
) -> HttpResponse:
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
    # 1. Validate content-type
    ct_response = _check_content_type(request)
    if ct_response is not None:
        return ct_response

    # 2. Validate payload size
    size_response = _check_payload_size(request)
    if size_response is not None:
        return size_response

    if repository is None:
        from sendparcel_django.repository import DjangoShipmentRepository

        repository = cast(ShipmentRepository, DjangoShipmentRepository())

    # 3. Parse JSON
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

    # 4. Build CallbackContext
    ctx = CallbackContext(
        shipment_id=shipment_id,
        payload=payload,
        headers=dict(getattr(request, "headers", {})),
        source_ip=resolve_client_ip(request.META),
        raw_body=bytes(getattr(request, "body", b"")),
    )

    # 5. Create CallbackProcessor and call process()
    processor = CallbackProcessor(repository, config)

    try:
        outcome = await processor.process(ctx)
    except DuplicateCallbackError:
        # 6. Handle DuplicateCallbackError (return 200)
        logger.info("Duplicate webhook for shipment %s, skipping", shipment_id)
        return JsonResponse({"status": "accepted"}, status=200)
    except CommunicationError as exc:
        # 7. Handle CommunicationError (store retry, return error)
        await _store_failed_callback_for_retry(ctx, exc)
        return _exception_to_response(exc)
    except SendParcelException as exc:
        # 8. Handle other SendParcelException (return error)
        return _exception_to_response(exc)

    # 9. Serialize and return success response
    return JsonResponse(
        {
            "provider": str(outcome.shipment.provider),
            "status": "accepted",
            "shipment": _serialize_shipment(outcome.shipment),
            "update": _serialize_update(outcome.update),
        }
    )


def _serialize_shipment(shipment: Any) -> dict[str, str]:
    return {
        "id": str(shipment.id),
        "status": str(shipment.status),
        "provider": str(shipment.provider),
        "external_id": str(shipment.external_id),
        "tracking_number": str(shipment.tracking_number),
    }


def _serialize_update(update: Any) -> dict[str, Any]:
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
    ctx: CallbackContext,
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
            shipment_id=ctx.shipment_id,
            provider_slug="unknown",
            payload=ctx.payload,
            headers=ctx.headers,
            source_ip=ctx.source_ip,
            raw_body=ctx.raw_body,
        )
        logger.info(
            "Stored failed callback for retry (id=%s, shipment=%s, error=%s)",
            retry_id,
            ctx.shipment_id,
            exc,
        )
    except Exception as store_exc:
        logger.error(
            "Failed to store callback retry for shipment %s: %s",
            ctx.shipment_id,
            store_exc,
        )

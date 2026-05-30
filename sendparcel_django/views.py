"""Django views for callback endpoints."""

from __future__ import annotations

import ipaddress
import json
import logging
from typing import Any, cast

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
from sendparcel.protocols import ShipmentRepository
from sendparcel.types import ShipmentUpdateOutcome, ShipmentUpdateResult

from sendparcel_django.dedup import DjangoWebhookDedupStore
from sendparcel_django.registry import registry as django_registry

logger = logging.getLogger(__name__)

# Trusted source IPs for webhook validation.
# Providers that need IP validation should check the
# "x-validated-source-ip" header set here from
# request.META['REMOTE_ADDR'] (the actual TCP connection IP).
# This prevents spoofing via x-forwarded-for which is faked by any client.
_WEBHOOK_TRUSTED_IPS: list[ipaddress.IPv4Network] = []


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
    if dedup_store.is_duplicate(payload, shipment_id):
        logger.info("Duplicate webhook for shipment %s, skipping", shipment_id)
        return JsonResponse({"status": "accepted"}, status=200)

    # Validate source IP from the actual TCP connection, not from spoofable
    # headers. Pass the validated IP to the provider via a special header.
    source_ip = request.META.get("REMOTE_ADDR", "")
    headers: dict[str, str] = dict(getattr(request, "headers", {}))
    headers["x-validated-source-ip"] = source_ip

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
        )
    except CommunicationError as exc:
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
) -> ShipmentUpdateOutcome:
    shipment = await repository.get_by_id(shipment_id)
    return await flow.handle_callback(
        shipment,
        payload,
        headers,
        raw_body=raw_body,
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

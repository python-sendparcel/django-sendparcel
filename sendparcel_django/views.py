"""Django views for callback endpoints."""

from __future__ import annotations

import json

import anyio
from django.http import HttpRequest, JsonResponse
from sendparcel.exceptions import InvalidCallbackError
from sendparcel.flow import ShipmentFlow


def callback(
    request: HttpRequest,
    shipment_id: str,
    *,
    repository=None,
    config: dict | None = None,
) -> JsonResponse:
    """Handle provider callbacks through the core shipment flow."""
    if repository is None:
        return JsonResponse(
            {"detail": "Repository is required for callback processing."},
            status=500,
        )

    try:
        payload = (
            json.loads(request.body.decode("utf-8"))
            if getattr(request, "body", b"")
            else {}
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON payload."}, status=400)

    flow = ShipmentFlow(repository=repository, config=config or {})

    try:
        shipment = anyio.run(
            _handle_callback,
            flow,
            repository,
            shipment_id,
            payload,
            dict(getattr(request, "headers", {})),
            getattr(request, "body", b""),
        )
    except InvalidCallbackError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    return JsonResponse(
        {
            "shipment_id": str(shipment.id),
            "status": str(shipment.status),
            "received": True,
        }
    )


async def _handle_callback(
    flow: ShipmentFlow,
    repository,
    shipment_id: str,
    payload: dict,
    headers: dict,
    raw_body: bytes,
):
    shipment = await repository.get_by_id(shipment_id)
    return await flow.handle_callback(
        shipment,
        payload,
        headers,
        raw_body=raw_body,
    )

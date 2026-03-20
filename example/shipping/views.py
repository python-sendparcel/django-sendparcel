"""Views for the shipping example app."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, cast

import anyio
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.utils.html import format_html
from django.views.decorators.http import require_GET, require_POST
from sendparcel.flow import ShipmentFlow
from sendparcel.types import (
    AddressInfo,
    CreateLabelOutcome,
    CreateShipmentOutcome,
    LabelInfo,
    ParcelInfo,
    ShipmentUpdateOutcome,
)
from sendparcel_django.protocols import DjangoShipmentAdapter
from sendparcel_django.registry import registry

from shipping.forms import CreateShipmentForm
from shipping.models import Shipment

if TYPE_CHECKING:
    from sendparcel_django.repository import DjangoShipmentRepository


def _get_repository() -> DjangoShipmentRepository:
    """Get the Django shipment repository.

    Imports lazily to avoid circular import at module level
    when Django has not finished app loading yet.
    """
    # circular import workaround: DjangoShipmentRepository
    # references the swappable model which requires apps to be ready
    from sendparcel_django.repository import DjangoShipmentRepository

    return DjangoShipmentRepository()


def _get_provider_config() -> dict[str, dict[str, Any]]:
    """Read provider config from Django settings."""
    from django.conf import settings

    return cast(
        dict[str, dict[str, Any]],
        getattr(settings, "SENDPARCEL_PROVIDER_SETTINGS", {}),
    )


@require_GET
def shipment_list(request: HttpRequest) -> HttpResponse:
    """List all shipments."""
    shipments = Shipment._default_manager.all()
    return TemplateResponse(
        request,
        "shipping/shipment_list.html",
        {"shipments": shipments},
    )


def shipment_create(request: HttpRequest) -> HttpResponse:
    """Create a new shipment with address, parcel, and provider details."""
    provider_choices = registry.get_choices()

    if request.method == "POST":
        form = CreateShipmentForm(
            request.POST, provider_choices=provider_choices
        )
        if form.is_valid():
            provider_slug = form.cleaned_data["provider"]
            shipment_data = {
                k: v for k, v in form.cleaned_data.items() if k != "provider"
            }

            repository = _get_repository()
            flow = ShipmentFlow(
                repository=repository,
                config=_get_provider_config(),
                registry=registry,
            )

            try:
                create_outcome = anyio.run(
                    _async_create_shipment,
                    flow,
                    provider_slug,
                    shipment_data,
                )
                shipment = _as_example_shipment(create_outcome.shipment)
                shipment_pk = cast(Any, shipment).pk
                messages.success(
                    request,
                    format_html(
                        "Shipment #{} has been created. Tracking number: {}{}",
                        shipment_pk,
                        shipment.tracking_number or "-",
                        _label_message_suffix(create_outcome.label),
                    ),
                )
                return redirect("shipping:shipment_detail", pk=shipment_pk)
            except Exception as exc:
                messages.error(
                    request,
                    f"Shipment creation error: {exc}",
                )
    else:
        form = CreateShipmentForm(provider_choices=provider_choices)

    return TemplateResponse(
        request,
        "shipping/shipment_create.html",
        {"form": form},
    )


async def _async_create_shipment(
    flow: ShipmentFlow,
    provider_slug: str,
    shipment_data: dict[str, Any],
) -> CreateShipmentOutcome:
    """Async helper to create shipment via the core flow."""
    sender_address = cast(
        AddressInfo,
        {
            "name": shipment_data["sender_name"],
            "line1": shipment_data["sender_street"],
            "city": shipment_data["sender_city"],
            "postal_code": shipment_data["sender_postal_code"],
            "country_code": shipment_data["sender_country_code"],
        },
    )
    receiver_address = cast(
        AddressInfo,
        {
            "name": shipment_data["receiver_name"],
            "line1": shipment_data["receiver_street"],
            "city": shipment_data["receiver_city"],
            "postal_code": shipment_data["receiver_postal_code"],
            "country_code": shipment_data["receiver_country_code"],
        },
    )
    parcels = cast(
        list[ParcelInfo],
        [
            {
                "weight_kg": shipment_data["weight"],
                "width_cm": shipment_data["width"],
                "height_cm": shipment_data["height"],
                "length_cm": shipment_data["length"],
            }
        ],
    )
    return await flow.create_shipment(
        provider_slug,
        sender_address=sender_address,
        receiver_address=receiver_address,
        parcels=parcels,
        reference_id=shipment_data.get("reference_id", ""),
    )


@require_GET
def shipment_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Shipment details with tracking information."""
    shipment = get_object_or_404(Shipment, pk=pk)
    return TemplateResponse(
        request,
        "shipping/shipment_detail.html",
        {"shipment": shipment},
    )


@require_POST
def shipment_create_label(request: HttpRequest, pk: int) -> HttpResponse:
    """Generate label for shipment."""
    shipment = get_object_or_404(Shipment, pk=pk)

    repository = _get_repository()
    flow = ShipmentFlow(
        repository=repository,
        config=_get_provider_config(),
        registry=registry,
    )

    try:
        label_outcome = anyio.run(_async_create_label, flow, shipment)
        shipment = _as_example_shipment(label_outcome.shipment)
        shipment_pk = cast(Any, shipment).pk
        messages.success(
            request,
            format_html(
                "Label created for shipment #{}.{}",
                shipment_pk,
                _label_message_suffix(label_outcome.label),
            ),
        )
    except Exception as exc:
        messages.error(request, f"Label creation failed: {exc}")

    return redirect("shipping:shipment_detail", pk=pk)


@require_GET
def shipment_refresh_status(request: HttpRequest, pk: int) -> HttpResponse:
    """HTMX partial -- refreshed shipment status badge."""
    shipment = get_object_or_404(Shipment, pk=pk)

    repository = _get_repository()
    flow = ShipmentFlow(
        repository=repository,
        config=_get_provider_config(),
        registry=registry,
    )

    with contextlib.suppress(Exception):
        status_outcome = anyio.run(_async_refresh_status, flow, shipment)
        shipment = _as_example_shipment(status_outcome.shipment)

    return TemplateResponse(
        request,
        "partials/status_badge.html",
        {"shipment": shipment},
    )


def _label_message_suffix(label: LabelInfo | None) -> str:
    if not label:
        return ""
    label_url = label.get("url")
    if not isinstance(label_url, str) or not label_url:
        return ""
    return str(
        format_html(
            ' <a href="{}" target="_blank" rel="noopener">Open label</a>',
            label_url,
        )
    )


async def _async_create_label(
    flow: ShipmentFlow,
    shipment: Shipment,
) -> CreateLabelOutcome:
    adapter = cast(Any, DjangoShipmentAdapter(shipment))
    return await flow.create_label(adapter)


async def _async_refresh_status(
    flow: ShipmentFlow,
    shipment: Shipment,
) -> ShipmentUpdateOutcome:
    adapter = cast(Any, DjangoShipmentAdapter(shipment))
    return await flow.fetch_and_update_status(adapter)


def _as_example_shipment(shipment: Any) -> Shipment:
    if isinstance(shipment, DjangoShipmentAdapter):
        return cast(Shipment, cast(Any, shipment).wrapped)
    return cast(Shipment, shipment)

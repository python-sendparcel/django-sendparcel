"""Views for the shipping example app."""

from __future__ import annotations

import anyio
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.views.decorators.http import require_GET
from sendparcel.flow import ShipmentFlow
from sendparcel_django.registry import registry

from shipping.forms import CreateShipmentForm
from shipping.models import Shipment


def _get_repository():
    """Get the Django shipment repository.

    Imports lazily to avoid circular import at module level
    when Django has not finished app loading yet.
    """
    # circular import workaround: DjangoShipmentRepository
    # references the swappable model which requires apps to be ready
    from sendparcel_django.repository import DjangoShipmentRepository

    return DjangoShipmentRepository()


def _get_provider_config() -> dict:
    """Read provider config from Django settings."""
    from django.conf import settings

    return getattr(settings, "SENDPARCEL_PROVIDER_SETTINGS", {})


@require_GET
def shipment_list(request: HttpRequest) -> HttpResponse:
    """List all shipments."""
    shipments = Shipment.objects.all()
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
            )

            try:
                shipment = anyio.run(
                    _async_create_shipment,
                    flow,
                    provider_slug,
                    shipment_data,
                )
                messages.success(
                    request,
                    f"Shipment #{shipment.pk} has been created. "
                    f"Tracking number: {shipment.tracking_number}",
                )
                return redirect("shipping:shipment_detail", pk=shipment.pk)
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


async def _async_create_shipment(flow, provider_slug, shipment_data):
    """Async helper to create shipment via the core flow."""
    sender_address = {
        "name": shipment_data["sender_name"],
        "line1": shipment_data["sender_street"],
        "city": shipment_data["sender_city"],
        "postal_code": shipment_data["sender_postal_code"],
        "country_code": shipment_data["sender_country_code"],
    }
    receiver_address = {
        "name": shipment_data["receiver_name"],
        "line1": shipment_data["receiver_street"],
        "city": shipment_data["receiver_city"],
        "postal_code": shipment_data["receiver_postal_code"],
        "country_code": shipment_data["receiver_country_code"],
    }
    parcels = [
        {
            "weight_kg": shipment_data["weight"],
            "width_cm": shipment_data["width"],
            "height_cm": shipment_data["height"],
            "length_cm": shipment_data["length"],
        }
    ]
    shipment = await flow.create_shipment(
        provider_slug,
        sender_address=sender_address,
        receiver_address=receiver_address,
        parcels=parcels,
        reference_id=shipment_data.get("reference_id", ""),
    )
    if not shipment.label_url:
        shipment = await flow.create_label(shipment)
    return shipment


@require_GET
def shipment_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Shipment details with tracking information."""
    shipment = get_object_or_404(Shipment, pk=pk)
    return TemplateResponse(
        request,
        "shipping/shipment_detail.html",
        {"shipment": shipment},
    )


@require_GET
def shipment_tracking(request: HttpRequest, pk: int) -> HttpResponse:
    """HTMX partial -- refreshed shipment status."""
    shipment = get_object_or_404(Shipment, pk=pk)
    return TemplateResponse(
        request,
        "shipping/shipment_tracking.html",
        {"shipment": shipment},
    )

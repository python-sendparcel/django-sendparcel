"""Views for the shipping example app."""

from __future__ import annotations

import anyio
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.views.decorators.http import require_GET, require_POST
from sendparcel.flow import ShipmentFlow
from sendparcel_django.registry import registry

from shipping.forms import CreateShipmentForm, OrderForm
from shipping.models import Order, Shipment


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
def order_list(request: HttpRequest) -> HttpResponse:
    """List orders with shipment information."""
    orders = Order.objects.prefetch_related("shipments").all()
    return TemplateResponse(
        request,
        "shipping/order_list.html",
        {"orders": orders},
    )


@require_GET
def order_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Order details with shipment creation form."""
    order = get_object_or_404(
        Order.objects.prefetch_related("shipments"), pk=pk
    )
    provider_choices = registry.get_choices()
    shipment_form = CreateShipmentForm(provider_choices=provider_choices)
    return TemplateResponse(
        request,
        "shipping/order_detail.html",
        {
            "order": order,
            "shipment_form": shipment_form,
        },
    )


def order_create(request: HttpRequest) -> HttpResponse:
    """Create a new order."""
    if request.method == "POST":
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save()
            messages.success(
                request,
                f"Order #{order.pk} has been created.",
            )
            return redirect("shipping:order_detail", pk=order.pk)
    else:
        form = OrderForm()

    return TemplateResponse(
        request,
        "shipping/order_create.html",
        {"form": form},
    )


@require_POST
def create_shipment(request: HttpRequest, order_pk: int) -> HttpResponse:
    """Create a shipment for an order via ShipmentFlow."""
    order = get_object_or_404(Order, pk=order_pk)
    provider_choices = registry.get_choices()
    form = CreateShipmentForm(request.POST, provider_choices=provider_choices)

    if not form.is_valid():
        messages.error(request, "Please select a valid provider.")
        return redirect("shipping:order_detail", pk=order.pk)

    provider_slug = form.cleaned_data["provider"]
    repository = _get_repository()
    flow = ShipmentFlow(
        repository=repository,
        config=_get_provider_config(),
    )

    try:
        shipment = anyio.run(_async_create_shipment, flow, order, provider_slug)
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
        return redirect("shipping:order_detail", pk=order.pk)


async def _async_create_shipment(flow, order, provider_slug):
    """Async helper to create shipment via the core flow."""
    from sendparcel_django.protocols import DjangoOrderAdapter

    adapted_order = DjangoOrderAdapter(wrapped=order)
    shipment = await flow.create_shipment(adapted_order, provider_slug)
    if not shipment.label_url:
        shipment = await flow.create_label(shipment)
    return shipment


@require_GET
def shipment_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Shipment details with tracking information."""
    shipment = get_object_or_404(
        Shipment.objects.select_related("order"), pk=pk
    )
    return TemplateResponse(
        request,
        "shipping/shipment_detail.html",
        {"shipment": shipment},
    )


@require_GET
def shipment_tracking(request: HttpRequest, pk: int) -> HttpResponse:
    """HTMX partial — refreshed shipment status."""
    shipment = get_object_or_404(Shipment, pk=pk)
    return TemplateResponse(
        request,
        "shipping/shipment_tracking.html",
        {"shipment": shipment},
    )

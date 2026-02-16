"""Delivery simulator views — operator dashboard and label endpoint."""

from __future__ import annotations

import json
import urllib.request

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from shipping.models import Shipment


def _get_sim_config() -> dict:
    """Read delivery-sim config from Django settings."""
    provider_settings = getattr(settings, "SENDPARCEL_PROVIDER_SETTINGS", {})
    return provider_settings.get("delivery-sim", {})


def _send_callback(shipment: Shipment, new_status: str) -> bool:
    """Send an HTTP callback to the sendparcel callback endpoint.

    Uses urllib so the example has zero extra dependencies.
    """
    config = _get_sim_config()
    token = config.get("callback_token", "example-sim-token-12345")

    callback_url = (
        f"http://localhost:8000"
        f"{reverse('sendparcel_django:callback', args=[shipment.pk])}"
    )

    payload = json.dumps({"status": new_status}).encode("utf-8")
    req = urllib.request.Request(
        callback_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Sim-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


@require_GET
def gateway(request: HttpRequest) -> HttpResponse:
    """Simulator dashboard — list shipments with action buttons."""
    shipments = Shipment.objects.select_related("order").all()
    return TemplateResponse(
        request,
        "delivery_sim/gateway.html",
        {"shipments": shipments},
    )


@require_POST
def trigger_status(request: HttpRequest, shipment_id: int) -> HttpResponse:
    """Trigger a status transition via callback."""
    shipment = get_object_or_404(Shipment, pk=shipment_id)
    new_status = request.POST.get("status", "")

    if new_status:
        _send_callback(shipment, new_status)

    return redirect("delivery_sim:gateway")


def _build_label_pdf(text: str) -> bytes:
    """Generate a minimal valid PDF with the given text."""
    stream = (f"BT /F1 14 Tf 72 760 Td ({_pdf_escape(text)}) Tj ET").encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 5 0 R >> >> "
            b"/Contents 4 0 R >>"
        ),
        (
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets:
        pdf.extend(f"{off:010} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} "
            f"/Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


@require_GET
def label_pdf(request: HttpRequest, shipment_id: str) -> HttpResponse:
    """Return a generated PDF label for a shipment."""
    label_text = f"Etykieta przesylki {shipment_id}"
    pdf_bytes = _build_label_pdf(label_text)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="label-{shipment_id}.pdf"'
    )
    return response

"""Delivery simulator views — operator dashboard and label endpoint."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.views.decorators.http import require_GET, require_POST
from sendparcel.enums import ShipmentStatus

from delivery_sim.provider import (
    get_next_statuses,
    get_sim_status,
    update_sim_status,
)

STATUS_LABELS: dict[str, str] = {
    ShipmentStatus.NEW: "New",
    ShipmentStatus.CREATED: "Created",
    ShipmentStatus.LABEL_READY: "Label ready",
    ShipmentStatus.IN_TRANSIT: "In transit",
    ShipmentStatus.OUT_FOR_DELIVERY: "Out for delivery",
    ShipmentStatus.DELIVERED: "Delivered",
    ShipmentStatus.CANCELLED: "Cancelled",
    ShipmentStatus.FAILED: "Failed",
    ShipmentStatus.RETURNED: "Returned",
}


@require_GET
def sim_panel(request: HttpRequest, shipment_id: int) -> HttpResponse:
    """Render simulator control panel partial (HTMX target)."""
    sid = str(shipment_id)
    current = get_sim_status(sid)
    next_options = get_next_statuses(current)

    return TemplateResponse(
        request,
        "partials/sim_panel.html",
        {
            "shipment_id": shipment_id,
            "current_status": current,
            "current_label": STATUS_LABELS.get(current, current),
            "next_options": [
                {"value": s, "label": STATUS_LABELS.get(s, s)}
                for s in next_options
            ],
        },
    )


@require_POST
def sim_advance(request: HttpRequest, shipment_id: int) -> HttpResponse:
    """Advance simulator status for a shipment (HTMX)."""
    sid = str(shipment_id)
    # HTMX sends form data, but if using json-enc extension it might be JSON.
    # Standard hx-post sends form-encoded data.
    new_status = request.POST.get("status", "")

    current = get_sim_status(sid)
    allowed = get_next_statuses(current)

    if new_status in allowed:
        update_sim_status(sid, new_status)

    # Re-render panel
    return sim_panel(request, shipment_id)


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
    label_text = f"Shipment label {shipment_id}"
    pdf_bytes = _build_label_pdf(label_text)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="label-{shipment_id}.pdf"'
    )
    return response

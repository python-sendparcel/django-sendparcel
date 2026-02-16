"""Template tags for django-sendparcel."""

from __future__ import annotations

from django import template
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from sendparcel_django.registry import registry

register = template.Library()

STATUS_COLORS: dict[str, str] = {
    "new": "bg-info",
    "created": "bg-info",
    "label_ready": "bg-warning",
    "in_transit": "bg-primary",
    "out_for_delivery": "bg-primary",
    "delivered": "bg-success",
    "cancelled": "bg-secondary",
    "failed": "bg-danger",
    "returned": "bg-secondary",
}


@register.simple_tag
def shipment_status_badge(shipment) -> str:
    """Render a colored badge for the shipment status."""
    status = str(shipment.status)
    color = STATUS_COLORS.get(status, "bg-secondary")
    label = escape(status.replace("_", " "))
    return format_html(
        '<span class="badge {}">{}</span>',
        color,
        label,
    )


@register.simple_tag
def provider_choices() -> str:
    """Render <option> elements for each registered provider."""
    choices = registry.get_choices()
    if not choices:
        return ""
    parts = []
    for slug, display_name in choices:
        parts.append(
            format_html(
                '<option value="{}">{}</option>',
                slug,
                display_name,
            )
        )
    return mark_safe("".join(str(p) for p in parts))


@register.simple_tag
def tracking_info(shipment) -> str:
    """Render tracking number and optional label link."""
    tracking_number = str(getattr(shipment, "tracking_number", ""))
    label_url = str(getattr(shipment, "label_url", ""))

    if not tracking_number:
        return ""

    if label_url:
        return format_html(
            '<span class="tracking-info">{} '
            '<a href="{}" target="_blank">Label</a></span>',
            tracking_number,
            label_url,
        )
    return format_html(
        '<span class="tracking-info">{}</span>',
        tracking_number,
    )

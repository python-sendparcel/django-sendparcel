# Django Example App & Documentation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the single-file `examples/app.py` with a proper Django project demonstrating real-world integration of `django-sendparcel`, and set up Sphinx documentation with quickstart, configuration reference, and API docs.

**Architecture:** Create a standalone `example/` Django project with three apps: `example` (project config), `shipping` (concrete Order/Shipment models using library mixins, views, templates), and `delivery_sim` (fake delivery provider that simulates the full webhook callback lifecycle). The project uses Tabler UI for styling, HTMX for interactions, and Django template inheritance. Documentation uses Sphinx with furo theme, myst-parser for Markdown, and autodoc for API reference.

**Tech Stack:** Django 5.2, python-sendparcel, Tabler CSS (CDN), HTMX 1.9 (CDN), Sphinx, furo, myst-parser

**Depends on:** `2026-02-15-django-foundation.md` and `2026-02-15-django-features-and-tests.md` must be completed first (AppConfig, swappable models, DjangoShipmentRepository, admin, template tags, retry, exception middleware, comprehensive tests).

---

## Task 1: Create Example Project Skeleton

**Files:**
- Create: `example/manage.py`
- Create: `example/example/__init__.py`
- Create: `example/example/settings.py`
- Create: `example/example/urls.py`
- Create: `example/example/wsgi.py`
- Create: `example/shipping/__init__.py`
- Create: `example/shipping/apps.py`
- Create: `example/shipping/migrations/__init__.py`
- Create: `example/delivery_sim/__init__.py`
- Create: `example/delivery_sim/apps.py`
- Create: `example/delivery_sim/migrations/__init__.py`

**Step 1: Create `example/manage.py`**

```python
#!/usr/bin/env python
"""Django management command entry point for the example project."""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

**Step 2: Create `example/example/__init__.py`**

Empty file.

**Step 3: Create `example/example/settings.py`**

```python
"""Django settings for the sendparcel example project."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "example-insecure-key-do-not-use-in-production"

DEBUG = True

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "sendparcel_django",
    "shipping",
    "delivery_sim",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "sendparcel_django.middleware.SendParcelExceptionMiddleware",
]

ROOT_URLCONF = "example.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "example.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "pl"
TIME_ZONE = "Europe/Warsaw"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- sendparcel settings ---
SENDPARCEL_SHIPMENT_MODEL = "shipping.Shipment"

SENDPARCEL_PROVIDER_SETTINGS = {
    "delivery-sim": {
        "api_url": os.environ.get(
            "DELIVERY_SIM_URL", "http://localhost:8000/delivery-sim/"
        ),
        "callback_token": "example-sim-token-12345",
    },
}
```

**Step 4: Create `example/example/urls.py`**

```python
"""Root URL configuration for the example project."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sendparcel/", include("sendparcel_django.urls")),
    path("delivery-sim/", include("delivery_sim.urls")),
    path("", include("shipping.urls")),
]
```

**Step 5: Create `example/example/wsgi.py`**

```python
"""WSGI config for the example project."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example.settings")

application = get_wsgi_application()
```

**Step 6: Create `example/shipping/__init__.py`**

Empty file.

**Step 7: Create `example/shipping/apps.py`**

```python
"""Shipping app configuration."""

from django.apps import AppConfig


class ShippingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shipping"
    verbose_name = "Wysyłki"
```

**Step 8: Create `example/shipping/migrations/__init__.py`**

Empty file.

**Step 9: Create `example/delivery_sim/__init__.py`**

Empty file.

**Step 10: Create `example/delivery_sim/apps.py`**

```python
"""Delivery simulator app configuration."""

from django.apps import AppConfig


class DeliverySimConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "delivery_sim"
    verbose_name = "Symulator dostawy"
```

**Step 11: Create `example/delivery_sim/migrations/__init__.py`**

Empty file.

**Step 12: Verify the directory structure exists**

Run: `find example/ -type f | sort`
Expected: All files listed above are present.

**Step 13: Commit**

```bash
git add example/
git commit -m "feat(example): create project skeleton with settings, urls, and app configs"
```

---

## Task 2: Create Shipping App Models

**Files:**
- Create: `example/shipping/models.py`

**Step 1: Create shipping models**

```python
"""Concrete Order and Shipment models for the example project."""

from decimal import Decimal

from django.db import models
from sendparcel_django.models import OrderModelMixin, ShipmentModelMixin


class Order(OrderModelMixin):
    """Demo order demonstrating sendparcel integration."""

    PACKAGE_SIZE_CHOICES = [
        ("S", "Mały (do 1 kg)"),
        ("M", "Średni (do 5 kg)"),
        ("L", "Duży (do 15 kg)"),
    ]

    PACKAGE_WEIGHTS = {
        "S": Decimal("0.5"),
        "M": Decimal("2.5"),
        "L": Decimal("10.0"),
    }

    description = models.CharField("opis", max_length=255)
    package_size = models.CharField(
        "rozmiar paczki",
        max_length=2,
        choices=PACKAGE_SIZE_CHOICES,
        default="M",
    )

    # Sender (warehouse) fields — fixed for the demo
    sender_name = models.CharField(
        "nazwa nadawcy", max_length=128, default="Przykładowy Magazyn"
    )
    sender_line1 = models.CharField(
        "adres nadawcy", max_length=255, default="ul. Magazynowa 1"
    )
    sender_city = models.CharField(
        "miasto nadawcy", max_length=128, default="Warszawa"
    )
    sender_postal_code = models.CharField(
        "kod pocztowy nadawcy", max_length=16, default="00-001"
    )

    # Recipient fields
    recipient_name = models.CharField("nazwa odbiorcy", max_length=128)
    recipient_email = models.EmailField("e-mail odbiorcy")
    recipient_phone = models.CharField("telefon odbiorcy", max_length=32)
    recipient_line1 = models.CharField("adres odbiorcy", max_length=255)
    recipient_city = models.CharField("miasto odbiorcy", max_length=128)
    recipient_postal_code = models.CharField(
        "kod pocztowy odbiorcy", max_length=16
    )

    created_at = models.DateTimeField("utworzono", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "zamówienie"
        verbose_name_plural = "zamówienia"

    def __str__(self):
        return f"Zamówienie #{self.pk}: {self.description}"

    def get_total_weight(self):
        return self.PACKAGE_WEIGHTS.get(
            self.package_size, Decimal("2.5")
        )

    def get_parcels(self):
        return [
            {
                "weight_kg": self.get_total_weight(),
            }
        ]

    def get_sender_address(self):
        return {
            "name": self.sender_name,
            "line1": self.sender_line1,
            "city": self.sender_city,
            "postal_code": self.sender_postal_code,
            "country_code": "PL",
        }

    def get_receiver_address(self):
        return {
            "name": self.recipient_name,
            "line1": self.recipient_line1,
            "city": self.recipient_city,
            "postal_code": self.recipient_postal_code,
            "country_code": "PL",
            "email": self.recipient_email,
            "phone": self.recipient_phone,
        }


class Shipment(ShipmentModelMixin):
    """Concrete shipment for the example project."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="shipments",
        verbose_name="zamówienie",
    )
    created_at = models.DateTimeField("utworzono", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "przesyłka"
        verbose_name_plural = "przesyłki"

    def __str__(self):
        return f"Przesyłka #{self.pk} ({self.get_status_display()})"

    def get_status_display(self):
        """Return Polish status label."""
        status_labels = {
            "new": "Nowa",
            "created": "Utworzona",
            "label_ready": "Etykieta gotowa",
            "in_transit": "W transporcie",
            "out_for_delivery": "W doręczeniu",
            "delivered": "Doręczona",
            "cancelled": "Anulowana",
            "failed": "Błąd",
            "returned": "Zwrócona",
        }
        return status_labels.get(self.status, self.status)
```

**Step 2: Commit**

```bash
git add example/shipping/models.py
git commit -m "feat(example): add Order and Shipment models with Polish labels"
```

---

## Task 3: Create Delivery Simulator Provider

**Files:**
- Create: `example/delivery_sim/provider.py`

The delivery simulator is a `BaseProvider` subclass that:
- Generates deterministic external IDs and tracking numbers
- Returns label URLs pointing to the sim's own endpoint
- Verifies callbacks via a shared token
- Processes status update callbacks from the sim dashboard

**Step 1: Create the provider**

```python
"""Delivery simulator provider — a fake carrier for the example project."""

from typing import ClassVar

from sendparcel.exceptions import InvalidCallbackError
from sendparcel.fsm import STATUS_TO_CALLBACK
from sendparcel.provider import BaseProvider
from sendparcel.types import (
    LabelInfo,
    ShipmentCreateResult,
    ShipmentStatusResponse,
)


class DeliverySimProvider(BaseProvider):
    """Fake delivery provider for local development and demos."""

    slug: ClassVar[str] = "delivery-sim"
    display_name: ClassVar[str] = "Symulator Dostawy"
    supported_countries: ClassVar[list[str]] = ["PL"]
    supported_services: ClassVar[list[str]] = ["standard"]

    async def create_shipment(self, **kwargs) -> ShipmentCreateResult:
        shipment_id = str(self.shipment.id)
        return ShipmentCreateResult(
            external_id=f"SIM-{shipment_id}",
            tracking_number=f"SIM-TRK-{shipment_id}",
            label=LabelInfo(
                format="PDF",
                url=self._label_url(shipment_id),
            ),
        )

    async def create_label(self, **kwargs) -> LabelInfo:
        shipment_id = str(self.shipment.id)
        return LabelInfo(
            format="PDF",
            url=self._label_url(shipment_id),
        )

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        expected_token = self.get_setting(
            "callback_token", "example-sim-token-12345"
        )
        provided_token = headers.get("x-sim-token", "")
        if provided_token != expected_token:
            raise InvalidCallbackError(
                "Nieprawidłowy token zwrotny symulatora."
            )

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        status_value = data.get("status")
        if not status_value:
            return

        callback = STATUS_TO_CALLBACK.get(
            str(status_value), str(status_value)
        )
        trigger = getattr(self.shipment, callback, None)
        may_trigger = getattr(self.shipment, "may_trigger", None)
        if trigger is None or may_trigger is None:
            return
        if may_trigger(callback):
            trigger()

    async def fetch_shipment_status(
        self, **kwargs
    ) -> ShipmentStatusResponse:
        return ShipmentStatusResponse(
            status=self.shipment.status,
        )

    async def cancel_shipment(self, **kwargs) -> bool:
        return True

    def _label_url(self, shipment_id: str) -> str:
        base = self.get_setting(
            "api_url", "http://localhost:8000/delivery-sim/"
        )
        return f"{str(base).rstrip('/')}/label/{shipment_id}.pdf"
```

**Step 2: Commit**

```bash
git add example/delivery_sim/provider.py
git commit -m "feat(example): add DeliverySimProvider (fake carrier)"
```

---

## Task 4: Create Delivery Simulator Views and URLs

**Files:**
- Create: `example/delivery_sim/views.py`
- Create: `example/delivery_sim/urls.py`

The simulator dashboard lets the operator trigger status transitions (picked up, in transit, delivered, etc.) by sending HTTP callbacks back to the sendparcel callback endpoint.

**Step 1: Create `example/delivery_sim/views.py`**

```python
"""Delivery simulator views — operator dashboard and label endpoint."""

from __future__ import annotations

import urllib.request
import json

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from shipping.models import Shipment


def _get_sim_config() -> dict:
    """Read delivery-sim config from Django settings."""
    provider_settings = getattr(
        settings, "SENDPARCEL_PROVIDER_SETTINGS", {}
    )
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
def trigger_status(
    request: HttpRequest, shipment_id: int
) -> HttpResponse:
    """Trigger a status transition via callback."""
    shipment = get_object_or_404(Shipment, pk=shipment_id)
    new_status = request.POST.get("status", "")

    if new_status:
        _send_callback(shipment, new_status)

    return redirect("delivery_sim:gateway")


def _build_label_pdf(text: str) -> bytes:
    """Generate a minimal valid PDF with the given text."""
    stream = (
        f"BT /F1 14 Tf 72 760 Td ({_pdf_escape(text)}) Tj ET"
    ).encode()
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
    pdf.extend(
        f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    )
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
    return (
        value.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


@require_GET
def label_pdf(
    request: HttpRequest, shipment_id: str
) -> HttpResponse:
    """Return a generated PDF label for a shipment."""
    label_text = f"Etykieta przesylki {shipment_id}"
    pdf_bytes = _build_label_pdf(label_text)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="label-{shipment_id}.pdf"'
    )
    return response
```

**Step 2: Create `example/delivery_sim/urls.py`**

```python
"""URL patterns for the delivery simulator."""

from django.urls import path

from delivery_sim import views

app_name = "delivery_sim"

urlpatterns = [
    path("", views.gateway, name="gateway"),
    path(
        "trigger/<int:shipment_id>/",
        views.trigger_status,
        name="trigger_status",
    ),
    path(
        "label/<str:shipment_id>.pdf",
        views.label_pdf,
        name="label_pdf",
    ),
]
```

**Step 3: Commit**

```bash
git add example/delivery_sim/views.py example/delivery_sim/urls.py
git commit -m "feat(example): add delivery simulator views and URLs"
```

---

## Task 5: Create Base Template with Tabler

**Files:**
- Create: `example/templates/base.html`

All user-facing text in Polish. Uses Tabler CSS from CDN (same beta20 version as the original example) and HTMX from CDN.

**Step 1: Create `example/templates/base.html`**

```html
<!doctype html>
<html lang="pl">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{% block title %}SendParcel Demo{% endblock %}</title>
    <link
      href="https://cdn.jsdelivr.net/npm/@tabler/core@1.0.0-beta20/dist/css/tabler.min.css"
      rel="stylesheet"
    />
    <script
      src="https://unpkg.com/htmx.org@1.9.12"
      integrity="sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2"
      crossorigin="anonymous"
    ></script>
    {% block extra_head %}{% endblock %}
  </head>
  <body class="layout-fluid">
    <aside class="navbar navbar-vertical navbar-expand-lg">
      <div class="container-fluid">
        <h1 class="navbar-brand navbar-brand-autodark">
          <a href="{% url 'shipping:order_list' %}">
            SendParcel Demo
          </a>
        </h1>
        <div class="collapse navbar-collapse" id="sidebar-menu">
          <ul class="navbar-nav pt-lg-3">
            <li class="nav-item">
              <a
                class="nav-link"
                href="{% url 'shipping:order_list' %}"
              >
                <span class="nav-link-icon">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    class="icon"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    stroke-width="2"
                    stroke="currentColor"
                    fill="none"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  >
                    <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                    <path d="M12 3l8 4.5l0 9l-8 4.5l-8 -4.5l0 -9l8 -4.5" />
                    <path d="M12 12l8 -4.5" />
                    <path d="M12 12l0 9" />
                    <path d="M12 12l-8 -4.5" />
                  </svg>
                </span>
                <span class="nav-link-title">Zamówienia</span>
              </a>
            </li>
            <li class="nav-item">
              <a
                class="nav-link"
                href="{% url 'shipping:order_create' %}"
              >
                <span class="nav-link-icon">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    class="icon"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    stroke-width="2"
                    stroke="currentColor"
                    fill="none"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  >
                    <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                    <path d="M12 5l0 14" />
                    <path d="M5 12l14 0" />
                  </svg>
                </span>
                <span class="nav-link-title">Nowe zamówienie</span>
              </a>
            </li>
            <li class="nav-item">
              <a
                class="nav-link"
                href="{% url 'delivery_sim:gateway' %}"
              >
                <span class="nav-link-icon">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    class="icon"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    stroke-width="2"
                    stroke="currentColor"
                    fill="none"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  >
                    <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                    <path d="M7 4v16l13 -8z" />
                  </svg>
                </span>
                <span class="nav-link-title">Symulator dostawy</span>
              </a>
            </li>
            <li class="nav-item">
              <a class="nav-link" href="{% url 'admin:index' %}">
                <span class="nav-link-icon">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    class="icon"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    stroke-width="2"
                    stroke="currentColor"
                    fill="none"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  >
                    <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                    <path
                      d="M10.325 4.317c.426 -1.756 2.924 -1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543 -.94 3.31 .826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756 .426 1.756 2.924 0 3.35a1.724 1.724 0 0 0 -1.066 2.573c.94 1.543 -.826 3.31 -2.37 2.37a1.724 1.724 0 0 0 -2.572 1.065c-.426 1.756 -2.924 1.756 -3.35 0a1.724 1.724 0 0 0 -2.573 -1.066c-1.543 .94 -3.31 -.826 -2.37 -2.37a1.724 1.724 0 0 0 -1.065 -2.572c-1.756 -.426 -1.756 -2.924 0 -3.35a1.724 1.724 0 0 0 1.066 -2.573c-.94 -1.543 .826 -3.31 2.37 -2.37c1 .608 2.296 .07 2.572 -1.065z"
                    />
                    <path d="M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0 -6 0" />
                  </svg>
                </span>
                <span class="nav-link-title">Admin</span>
              </a>
            </li>
          </ul>
        </div>
      </div>
    </aside>
    <div class="page-wrapper">
      <div class="page-header d-print-none">
        <div class="container-xl">
          <div class="page-pretitle">SendParcel Demo</div>
          <h2 class="page-title">
            {% block page_title %}{% endblock %}
          </h2>
        </div>
      </div>
      <div class="page-body">
        <div class="container-xl">
          {% if messages %}
            {% for message in messages %}
              <div
                class="alert alert-{{ message.tags|default:'info' }} alert-dismissible"
                role="alert"
              >
                <div class="d-flex">
                  <div>{{ message }}</div>
                </div>
                <a
                  class="btn-close"
                  data-bs-dismiss="alert"
                  aria-label="Zamknij"
                ></a>
              </div>
            {% endfor %}
          {% endif %}
          {% block content %}{% endblock %}
        </div>
      </div>
    </div>
    <script
      src="https://cdn.jsdelivr.net/npm/@tabler/core@1.0.0-beta20/dist/js/tabler.min.js"
    ></script>
  </body>
</html>
```

**Step 2: Commit**

```bash
git add example/templates/base.html
git commit -m "feat(example): add Tabler base template with Polish navigation"
```

---

## Task 6: Create Shipping App Forms

**Files:**
- Create: `example/shipping/forms.py`

**Step 1: Create forms**

```python
"""Forms for the shipping example app."""

from django import forms

from shipping.models import Order


class OrderForm(forms.ModelForm):
    """Form for creating a new order."""

    class Meta:
        model = Order
        fields = [
            "description",
            "package_size",
            "recipient_name",
            "recipient_email",
            "recipient_phone",
            "recipient_line1",
            "recipient_city",
            "recipient_postal_code",
        ]
        widgets = {
            "description": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "np. Elektronika, Książki",
                }
            ),
            "package_size": forms.Select(attrs={"class": "form-select"}),
            "recipient_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Jan Kowalski",
                }
            ),
            "recipient_email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "jan@example.com",
                }
            ),
            "recipient_phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "+48 123 456 789",
                }
            ),
            "recipient_line1": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "ul. Przykładowa 10/2",
                }
            ),
            "recipient_city": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Kraków",
                }
            ),
            "recipient_postal_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "30-001",
                }
            ),
        }


class CreateShipmentForm(forms.Form):
    """Form for creating a shipment from an order."""

    provider = forms.ChoiceField(
        label="Dostawca",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        provider_choices = kwargs.pop("provider_choices", [])
        super().__init__(*args, **kwargs)
        self.fields["provider"].choices = provider_choices
```

**Step 2: Commit**

```bash
git add example/shipping/forms.py
git commit -m "feat(example): add OrderForm and CreateShipmentForm"
```

---

## Task 7: Create Shipping App Views

**Files:**
- Create: `example/shipping/views.py`

Views use synchronous Django views with `anyio.run()` for async core calls (same pattern as the library's callback view).

**Step 1: Create views**

```python
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


@require_GET
def order_list(request: HttpRequest) -> HttpResponse:
    """Lista zamówień z informacją o przesyłkach."""
    orders = Order.objects.prefetch_related("shipments").all()
    return TemplateResponse(
        request,
        "shipping/order_list.html",
        {"orders": orders},
    )


@require_GET
def order_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Szczegóły zamówienia z formularzem tworzenia przesyłki."""
    order = get_object_or_404(
        Order.objects.prefetch_related("shipments"), pk=pk
    )
    provider_choices = registry.get_choices()
    shipment_form = CreateShipmentForm(
        provider_choices=provider_choices
    )
    return TemplateResponse(
        request,
        "shipping/order_detail.html",
        {
            "order": order,
            "shipment_form": shipment_form,
        },
    )


def order_create(request: HttpRequest) -> HttpResponse:
    """Tworzenie nowego zamówienia."""
    if request.method == "POST":
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save()
            messages.success(
                request,
                f"Zamówienie #{order.pk} zostało utworzone.",
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
def create_shipment(
    request: HttpRequest, order_pk: int
) -> HttpResponse:
    """Utwórz przesyłkę dla zamówienia przez ShipmentFlow."""
    order = get_object_or_404(Order, pk=order_pk)
    provider_choices = registry.get_choices()
    form = CreateShipmentForm(
        request.POST, provider_choices=provider_choices
    )

    if not form.is_valid():
        messages.error(request, "Wybierz prawidłowego dostawcę.")
        return redirect("shipping:order_detail", pk=order.pk)

    provider_slug = form.cleaned_data["provider"]
    repository = _get_repository()
    flow = ShipmentFlow(
        repository=repository,
        config=_get_provider_config(),
    )

    try:
        shipment = anyio.run(
            _async_create_shipment, flow, order, provider_slug
        )
        messages.success(
            request,
            f"Przesyłka #{shipment.pk} została utworzona. "
            f"Numer śledzenia: {shipment.tracking_number}",
        )
        return redirect("shipping:shipment_detail", pk=shipment.pk)
    except Exception as exc:
        messages.error(
            request,
            f"Błąd tworzenia przesyłki: {exc}",
        )
        return redirect("shipping:order_detail", pk=order.pk)


async def _async_create_shipment(flow, order, provider_slug):
    """Async helper to create shipment via the core flow."""
    from sendparcel_django.protocols import DjangoOrderAdapter

    adapted_order = DjangoOrderAdapter(wrapped=order)
    return await flow.create_shipment(adapted_order, provider_slug)


@require_GET
def shipment_detail(
    request: HttpRequest, pk: int
) -> HttpResponse:
    """Szczegóły przesyłki z informacją o śledzeniu."""
    shipment = get_object_or_404(
        Shipment.objects.select_related("order"), pk=pk
    )
    return TemplateResponse(
        request,
        "shipping/shipment_detail.html",
        {"shipment": shipment},
    )


@require_GET
def shipment_tracking(
    request: HttpRequest, pk: int
) -> HttpResponse:
    """HTMX partial — odświeżony status przesyłki."""
    shipment = get_object_or_404(Shipment, pk=pk)
    return TemplateResponse(
        request,
        "shipping/shipment_tracking.html",
        {"shipment": shipment},
    )


def _get_provider_config() -> dict:
    """Read provider config from Django settings."""
    from django.conf import settings

    return getattr(settings, "SENDPARCEL_PROVIDER_SETTINGS", {})
```

**Step 2: Commit**

```bash
git add example/shipping/views.py
git commit -m "feat(example): add shipping views (list, detail, create, tracking)"
```

---

## Task 8: Create Shipping App URLs and Admin

**Files:**
- Create: `example/shipping/urls.py`
- Create: `example/shipping/admin.py`

**Step 1: Create `example/shipping/urls.py`**

```python
"""URL patterns for the shipping example app."""

from django.urls import path

from shipping import views

app_name = "shipping"

urlpatterns = [
    path("", views.order_list, name="order_list"),
    path(
        "zamowienie/nowe/",
        views.order_create,
        name="order_create",
    ),
    path(
        "zamowienie/<int:pk>/",
        views.order_detail,
        name="order_detail",
    ),
    path(
        "zamowienie/<int:order_pk>/wyslij/",
        views.create_shipment,
        name="create_shipment",
    ),
    path(
        "przesylka/<int:pk>/",
        views.shipment_detail,
        name="shipment_detail",
    ),
    path(
        "przesylka/<int:pk>/tracking/",
        views.shipment_tracking,
        name="shipment_tracking",
    ),
]
```

**Step 2: Create `example/shipping/admin.py`**

```python
"""Admin configuration for the shipping example app."""

from django.contrib import admin

from shipping.models import Order, Shipment


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "description",
        "package_size",
        "recipient_name",
        "recipient_city",
        "created_at",
    ]
    list_filter = ["package_size", "created_at"]
    search_fields = [
        "description",
        "recipient_name",
        "recipient_email",
    ]


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "order",
        "provider",
        "status",
        "tracking_number",
        "created_at",
    ]
    list_filter = ["status", "provider"]
    search_fields = ["tracking_number", "external_id"]
    raw_id_fields = ["order"]
```

**Step 3: Commit**

```bash
git add example/shipping/urls.py example/shipping/admin.py
git commit -m "feat(example): add shipping URLs and admin registration"
```

---

## Task 9: Create Shipping Templates

**Files:**
- Create: `example/templates/shipping/order_list.html`
- Create: `example/templates/shipping/order_create.html`
- Create: `example/templates/shipping/order_detail.html`
- Create: `example/templates/shipping/shipment_detail.html`
- Create: `example/templates/shipping/shipment_tracking.html`

**Step 1: Create `example/templates/shipping/order_list.html`**

```html
{% extends "base.html" %}

{% block title %}Zamówienia — SendParcel Demo{% endblock %}

{% block page_title %}Zamówienia{% endblock %}

{% block content %}
<div class="card">
  <div class="card-header">
    <h3 class="card-title">Lista zamówień</h3>
    <div class="card-actions">
      <a href="{% url 'shipping:order_create' %}" class="btn btn-primary">
        Nowe zamówienie
      </a>
    </div>
  </div>
  {% if orders %}
    <div class="table-responsive">
      <table class="table table-vcenter card-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Opis</th>
            <th>Odbiorca</th>
            <th>Rozmiar</th>
            <th>Przesyłki</th>
            <th>Utworzono</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {% for order in orders %}
            <tr>
              <td>{{ order.pk }}</td>
              <td>{{ order.description }}</td>
              <td>{{ order.recipient_name }}</td>
              <td>
                <span class="badge bg-blue-lt">
                  {{ order.get_package_size_display }}
                </span>
              </td>
              <td>
                {% for shipment in order.shipments.all %}
                  <a
                    href="{% url 'shipping:shipment_detail' pk=shipment.pk %}"
                    class="badge bg-{{ shipment.status|default:'secondary' }}-lt"
                  >
                    {{ shipment.get_status_display }}
                  </a>
                {% empty %}
                  <span class="text-secondary">Brak</span>
                {% endfor %}
              </td>
              <td>{{ order.created_at|date:"d.m.Y H:i" }}</td>
              <td>
                <a
                  href="{% url 'shipping:order_detail' pk=order.pk %}"
                  class="btn btn-sm"
                >
                  Szczegóły
                </a>
              </td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  {% else %}
    <div class="card-body">
      <div class="empty">
        <p class="empty-title">Brak zamówień</p>
        <p class="empty-subtitle text-secondary">
          Utwórz pierwsze zamówienie, aby rozpocząć.
        </p>
        <div class="empty-action">
          <a
            href="{% url 'shipping:order_create' %}"
            class="btn btn-primary"
          >
            Nowe zamówienie
          </a>
        </div>
      </div>
    </div>
  {% endif %}
</div>
{% endblock %}
```

**Step 2: Create `example/templates/shipping/order_create.html`**

```html
{% extends "base.html" %}

{% block title %}Nowe zamówienie — SendParcel Demo{% endblock %}

{% block page_title %}Nowe zamówienie{% endblock %}

{% block content %}
<div class="row justify-content-center">
  <div class="col-lg-8">
    <form method="post" action="{% url 'shipping:order_create' %}">
      {% csrf_token %}
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Dane zamówienia</h3>
        </div>
        <div class="card-body">
          <div class="row g-3">
            <div class="col-md-8">
              <label class="form-label" for="id_description">Opis</label>
              {{ form.description }}
              {% if form.description.errors %}
                <div class="invalid-feedback d-block">
                  {{ form.description.errors.0 }}
                </div>
              {% endif %}
            </div>
            <div class="col-md-4">
              <label class="form-label" for="id_package_size">
                Rozmiar paczki
              </label>
              {{ form.package_size }}
              {% if form.package_size.errors %}
                <div class="invalid-feedback d-block">
                  {{ form.package_size.errors.0 }}
                </div>
              {% endif %}
            </div>
          </div>

          <h4 class="mt-4 mb-3">Dane odbiorcy</h4>
          <div class="row g-3">
            <div class="col-md-6">
              <label class="form-label" for="id_recipient_name">
                Imię i nazwisko
              </label>
              {{ form.recipient_name }}
              {% if form.recipient_name.errors %}
                <div class="invalid-feedback d-block">
                  {{ form.recipient_name.errors.0 }}
                </div>
              {% endif %}
            </div>
            <div class="col-md-6">
              <label class="form-label" for="id_recipient_email">
                E-mail
              </label>
              {{ form.recipient_email }}
              {% if form.recipient_email.errors %}
                <div class="invalid-feedback d-block">
                  {{ form.recipient_email.errors.0 }}
                </div>
              {% endif %}
            </div>
            <div class="col-md-4">
              <label class="form-label" for="id_recipient_phone">
                Telefon
              </label>
              {{ form.recipient_phone }}
              {% if form.recipient_phone.errors %}
                <div class="invalid-feedback d-block">
                  {{ form.recipient_phone.errors.0 }}
                </div>
              {% endif %}
            </div>
            <div class="col-md-8">
              <label class="form-label" for="id_recipient_line1">
                Adres
              </label>
              {{ form.recipient_line1 }}
              {% if form.recipient_line1.errors %}
                <div class="invalid-feedback d-block">
                  {{ form.recipient_line1.errors.0 }}
                </div>
              {% endif %}
            </div>
            <div class="col-md-6">
              <label class="form-label" for="id_recipient_city">
                Miasto
              </label>
              {{ form.recipient_city }}
              {% if form.recipient_city.errors %}
                <div class="invalid-feedback d-block">
                  {{ form.recipient_city.errors.0 }}
                </div>
              {% endif %}
            </div>
            <div class="col-md-6">
              <label class="form-label" for="id_recipient_postal_code">
                Kod pocztowy
              </label>
              {{ form.recipient_postal_code }}
              {% if form.recipient_postal_code.errors %}
                <div class="invalid-feedback d-block">
                  {{ form.recipient_postal_code.errors.0 }}
                </div>
              {% endif %}
            </div>
          </div>
        </div>
        <div class="card-footer text-end">
          <a
            href="{% url 'shipping:order_list' %}"
            class="btn btn-link"
          >
            Anuluj
          </a>
          <button type="submit" class="btn btn-primary">
            Utwórz zamówienie
          </button>
        </div>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

**Step 3: Create `example/templates/shipping/order_detail.html`**

```html
{% extends "base.html" %}

{% block title %}Zamówienie #{{ order.pk }} — SendParcel Demo{% endblock %}

{% block page_title %}Zamówienie #{{ order.pk }}{% endblock %}

{% block content %}
<div class="row g-3">
  <div class="col-lg-7">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Szczegóły zamówienia</h3>
      </div>
      <div class="card-body">
        <div class="datagrid">
          <div class="datagrid-item">
            <div class="datagrid-title">Opis</div>
            <div class="datagrid-content">{{ order.description }}</div>
          </div>
          <div class="datagrid-item">
            <div class="datagrid-title">Rozmiar paczki</div>
            <div class="datagrid-content">
              <span class="badge bg-blue-lt">
                {{ order.get_package_size_display }}
              </span>
            </div>
          </div>
          <div class="datagrid-item">
            <div class="datagrid-title">Waga</div>
            <div class="datagrid-content">{{ order.get_total_weight }} kg</div>
          </div>
          <div class="datagrid-item">
            <div class="datagrid-title">Nadawca</div>
            <div class="datagrid-content">
              {{ order.sender_name }}<br />
              {{ order.sender_line1 }}<br />
              {{ order.sender_postal_code }} {{ order.sender_city }}
            </div>
          </div>
          <div class="datagrid-item">
            <div class="datagrid-title">Odbiorca</div>
            <div class="datagrid-content">
              {{ order.recipient_name }}<br />
              {{ order.recipient_line1 }}<br />
              {{ order.recipient_postal_code }} {{ order.recipient_city }}<br />
              {{ order.recipient_email }} | {{ order.recipient_phone }}
            </div>
          </div>
          <div class="datagrid-item">
            <div class="datagrid-title">Utworzono</div>
            <div class="datagrid-content">
              {{ order.created_at|date:"d.m.Y H:i" }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="col-lg-5">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Utwórz przesyłkę</h3>
      </div>
      <div class="card-body">
        <form
          method="post"
          action="{% url 'shipping:create_shipment' order_pk=order.pk %}"
        >
          {% csrf_token %}
          <div class="mb-3">
            <label class="form-label" for="id_provider">Dostawca</label>
            {{ shipment_form.provider }}
          </div>
          <button type="submit" class="btn btn-primary w-100">
            Utwórz przesyłkę
          </button>
        </form>
      </div>
    </div>

    {% if order.shipments.all %}
      <div class="card mt-3">
        <div class="card-header">
          <h3 class="card-title">Przesyłki</h3>
        </div>
        <div class="list-group list-group-flush">
          {% for shipment in order.shipments.all %}
            <a
              href="{% url 'shipping:shipment_detail' pk=shipment.pk %}"
              class="list-group-item list-group-item-action"
            >
              <div class="d-flex justify-content-between align-items-center">
                <div>
                  <strong>Przesyłka #{{ shipment.pk }}</strong>
                  <br />
                  <small class="text-secondary">
                    {{ shipment.provider }} |
                    {{ shipment.tracking_number|default:"—" }}
                  </small>
                </div>
                <span class="badge">{{ shipment.get_status_display }}</span>
              </div>
            </a>
          {% endfor %}
        </div>
      </div>
    {% endif %}
  </div>
</div>
{% endblock %}
```

**Step 4: Create `example/templates/shipping/shipment_detail.html`**

```html
{% extends "base.html" %}

{% block title %}Przesyłka #{{ shipment.pk }} — SendParcel Demo{% endblock %}

{% block page_title %}Przesyłka #{{ shipment.pk }}{% endblock %}

{% block content %}
<div class="row g-3">
  <div class="col-lg-8">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Szczegóły przesyłki</h3>
      </div>
      <div class="card-body">
        <div class="datagrid">
          <div class="datagrid-item">
            <div class="datagrid-title">Zamówienie</div>
            <div class="datagrid-content">
              <a href="{% url 'shipping:order_detail' pk=shipment.order.pk %}">
                #{{ shipment.order.pk }} — {{ shipment.order.description }}
              </a>
            </div>
          </div>
          <div class="datagrid-item">
            <div class="datagrid-title">Dostawca</div>
            <div class="datagrid-content">{{ shipment.provider }}</div>
          </div>
          <div class="datagrid-item">
            <div class="datagrid-title">ID zewnętrzne</div>
            <div class="datagrid-content">
              {{ shipment.external_id|default:"—" }}
            </div>
          </div>
          <div class="datagrid-item">
            <div class="datagrid-title">Numer śledzenia</div>
            <div class="datagrid-content">
              <strong>{{ shipment.tracking_number|default:"—" }}</strong>
            </div>
          </div>
          <div class="datagrid-item">
            <div class="datagrid-title">Utworzono</div>
            <div class="datagrid-content">
              {{ shipment.created_at|date:"d.m.Y H:i" }}
            </div>
          </div>
        </div>
      </div>
      {% if shipment.label_url %}
        <div class="card-footer">
          <a
            href="{{ shipment.label_url }}"
            class="btn btn-primary"
            target="_blank"
          >
            Pobierz etykietę (PDF)
          </a>
        </div>
      {% endif %}
    </div>
  </div>

  <div class="col-lg-4">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Status</h3>
      </div>
      <div
        id="tracking-panel"
        hx-get="{% url 'shipping:shipment_tracking' pk=shipment.pk %}"
        hx-trigger="every 3s"
        hx-swap="innerHTML"
      >
        {% include "shipping/shipment_tracking.html" %}
      </div>
    </div>
  </div>
</div>
{% endblock %}
```

**Step 5: Create `example/templates/shipping/shipment_tracking.html`**

This is an HTMX partial — it is both included directly and refreshed via polling.

```html
<div class="card-body">
  <div class="mb-3">
    <span class="status-dot
      {% if shipment.status == 'delivered' %}status-dot-green
      {% elif shipment.status == 'in_transit' or shipment.status == 'out_for_delivery' %}status-dot-yellow
      {% elif shipment.status == 'failed' or shipment.status == 'cancelled' %}status-dot-red
      {% else %}status-dot-blue
      {% endif %}
      status-dot-animated
    "></span>
    <strong>{{ shipment.get_status_display }}</strong>
  </div>

  <div class="steps steps-vertical">
    <span class="step-item {% if shipment.status == 'new' or shipment.status == 'created' or shipment.status == 'label_ready' or shipment.status == 'in_transit' or shipment.status == 'out_for_delivery' or shipment.status == 'delivered' %}active{% endif %}">
      Nowa
    </span>
    <span class="step-item {% if shipment.status == 'created' or shipment.status == 'label_ready' or shipment.status == 'in_transit' or shipment.status == 'out_for_delivery' or shipment.status == 'delivered' %}active{% endif %}">
      Utworzona
    </span>
    <span class="step-item {% if shipment.status == 'label_ready' or shipment.status == 'in_transit' or shipment.status == 'out_for_delivery' or shipment.status == 'delivered' %}active{% endif %}">
      Etykieta gotowa
    </span>
    <span class="step-item {% if shipment.status == 'in_transit' or shipment.status == 'out_for_delivery' or shipment.status == 'delivered' %}active{% endif %}">
      W transporcie
    </span>
    <span class="step-item {% if shipment.status == 'out_for_delivery' or shipment.status == 'delivered' %}active{% endif %}">
      W doręczeniu
    </span>
    <span class="step-item {% if shipment.status == 'delivered' %}active{% endif %}">
      Doręczona
    </span>
  </div>

  {% if shipment.status == 'cancelled' %}
    <div class="alert alert-danger mt-3 mb-0">
      Przesyłka została anulowana.
    </div>
  {% elif shipment.status == 'failed' %}
    <div class="alert alert-danger mt-3 mb-0">
      Wystąpił błąd przetwarzania przesyłki.
    </div>
  {% elif shipment.status == 'returned' %}
    <div class="alert alert-warning mt-3 mb-0">
      Przesyłka została zwrócona do nadawcy.
    </div>
  {% elif shipment.status == 'delivered' %}
    <div class="alert alert-success mt-3 mb-0">
      Przesyłka została doręczona.
    </div>
  {% endif %}
</div>
```

**Step 6: Commit**

```bash
git add example/templates/shipping/
git commit -m "feat(example): add shipping templates with Tabler UI and HTMX tracking"
```

---

## Task 10: Create Delivery Simulator Template

**Files:**
- Create: `example/templates/delivery_sim/gateway.html`

The simulator dashboard shows all shipments and lets the operator trigger status transitions.

**Step 1: Create `example/templates/delivery_sim/gateway.html`**

```html
{% extends "base.html" %}

{% block title %}Symulator dostawy — SendParcel Demo{% endblock %}

{% block page_title %}Symulator dostawy{% endblock %}

{% block content %}
<div class="card">
  <div class="card-header">
    <h3 class="card-title">Panel operatora</h3>
    <div class="card-actions">
      <span class="text-secondary">
        Symuluje zachowanie firmy kurierskiej.
        Kliknij przycisk, aby wysłać callback zmiany statusu.
      </span>
    </div>
  </div>
  {% if shipments %}
    <div class="table-responsive">
      <table class="table table-vcenter card-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Zamówienie</th>
            <th>Dostawca</th>
            <th>Numer śledzenia</th>
            <th>Status</th>
            <th>Akcje</th>
          </tr>
        </thead>
        <tbody>
          {% for shipment in shipments %}
            <tr>
              <td>{{ shipment.pk }}</td>
              <td>
                <a
                  href="{% url 'shipping:order_detail' pk=shipment.order.pk %}"
                >
                  #{{ shipment.order.pk }}
                </a>
              </td>
              <td>{{ shipment.provider }}</td>
              <td>
                <code>{{ shipment.tracking_number|default:"—" }}</code>
              </td>
              <td>
                <span class="badge">{{ shipment.get_status_display }}</span>
              </td>
              <td>
                <div class="btn-list">
                  {% if shipment.status == 'label_ready' or shipment.status == 'created' %}
                    <form
                      method="post"
                      action="{% url 'delivery_sim:trigger_status' shipment_id=shipment.pk %}"
                      class="d-inline"
                    >
                      {% csrf_token %}
                      <input
                        type="hidden"
                        name="status"
                        value="in_transit"
                      />
                      <button
                        type="submit"
                        class="btn btn-sm btn-yellow"
                      >
                        W transporcie
                      </button>
                    </form>
                  {% endif %}
                  {% if shipment.status == 'in_transit' %}
                    <form
                      method="post"
                      action="{% url 'delivery_sim:trigger_status' shipment_id=shipment.pk %}"
                      class="d-inline"
                    >
                      {% csrf_token %}
                      <input
                        type="hidden"
                        name="status"
                        value="out_for_delivery"
                      />
                      <button
                        type="submit"
                        class="btn btn-sm btn-cyan"
                      >
                        W doręczeniu
                      </button>
                    </form>
                    <form
                      method="post"
                      action="{% url 'delivery_sim:trigger_status' shipment_id=shipment.pk %}"
                      class="d-inline"
                    >
                      {% csrf_token %}
                      <input
                        type="hidden"
                        name="status"
                        value="delivered"
                      />
                      <button
                        type="submit"
                        class="btn btn-sm btn-green"
                      >
                        Doręczona
                      </button>
                    </form>
                  {% endif %}
                  {% if shipment.status == 'out_for_delivery' %}
                    <form
                      method="post"
                      action="{% url 'delivery_sim:trigger_status' shipment_id=shipment.pk %}"
                      class="d-inline"
                    >
                      {% csrf_token %}
                      <input
                        type="hidden"
                        name="status"
                        value="delivered"
                      />
                      <button
                        type="submit"
                        class="btn btn-sm btn-green"
                      >
                        Doręczona
                      </button>
                    </form>
                    <form
                      method="post"
                      action="{% url 'delivery_sim:trigger_status' shipment_id=shipment.pk %}"
                      class="d-inline"
                    >
                      {% csrf_token %}
                      <input
                        type="hidden"
                        name="status"
                        value="returned"
                      />
                      <button
                        type="submit"
                        class="btn btn-sm btn-orange"
                      >
                        Zwrócona
                      </button>
                    </form>
                  {% endif %}
                  {% if shipment.status == 'new' or shipment.status == 'created' or shipment.status == 'label_ready' %}
                    <form
                      method="post"
                      action="{% url 'delivery_sim:trigger_status' shipment_id=shipment.pk %}"
                      class="d-inline"
                    >
                      {% csrf_token %}
                      <input
                        type="hidden"
                        name="status"
                        value="cancelled"
                      />
                      <button
                        type="submit"
                        class="btn btn-sm btn-red"
                      >
                        Anuluj
                      </button>
                    </form>
                  {% endif %}
                </div>
              </td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  {% else %}
    <div class="card-body">
      <div class="empty">
        <p class="empty-title">Brak przesyłek</p>
        <p class="empty-subtitle text-secondary">
          Utwórz zamówienie i przesyłkę, aby zobaczyć je tutaj.
        </p>
      </div>
    </div>
  {% endif %}
</div>
{% endblock %}
```

**Step 2: Commit**

```bash
git add example/templates/delivery_sim/
git commit -m "feat(example): add delivery simulator dashboard template"
```

---

## Task 11: Register Provider and Create Migrations

**Files:**
- Modify: `example/delivery_sim/apps.py`

The delivery simulator provider must be registered with the sendparcel registry when the app is ready.

**Step 1: Update `example/delivery_sim/apps.py` to register the provider**

```python
"""Delivery simulator app configuration."""

from django.apps import AppConfig


class DeliverySimConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "delivery_sim"
    verbose_name = "Symulator dostawy"

    def ready(self):
        from sendparcel_django.registry import registry

        from delivery_sim.provider import DeliverySimProvider

        registry.register(DeliverySimProvider)
```

**Step 2: Create migrations**

Run: `python manage.py makemigrations shipping` (from `example/` directory)
Expected: Creates `example/shipping/migrations/0001_initial.py` with Order and Shipment models.

Run: `python manage.py makemigrations delivery_sim` (from `example/` directory)
Expected: "No changes detected" (delivery_sim has no models).

**Step 3: Apply migrations and verify**

Run: `python manage.py migrate` (from `example/` directory)
Expected: All migrations applied successfully.

**Step 4: Verify the server starts**

Run: `python manage.py runserver --noreload 0:8000` (from `example/` directory)
Expected: Server starts without errors. Stop it after verification.

**Step 5: Commit**

```bash
git add example/
git commit -m "feat(example): register DeliverySimProvider and create migrations"
```

---

## Task 12: Delete Old Example and Update References

**Files:**
- Delete: `examples/app.py`
- Delete: `examples/__pycache__/` (if present)
- Modify: `pyproject.toml` (remove per-file-ignores for `examples/app.py`)
- Modify: `tests/test_example_app.py` (remove or replace)

**Step 1: Delete old example file**

Run: `rm -rf examples/`

**Step 2: Remove per-file-ignores from pyproject.toml**

In `pyproject.toml`, remove the line:

```toml
"examples/app.py" = ["E501"]
```

from `[tool.ruff.lint.per-file-ignores]`. If that section becomes empty, remove the entire section.

**Step 3: Update or remove `tests/test_example_app.py`**

The existing test tests the old inline-HTML example. Remove it — the new example project is a full Django project that should be tested manually or with its own test suite.

Run: `rm tests/test_example_app.py`

**Step 4: Run existing tests to verify nothing is broken**

Run: `uv run pytest tests/ -v`
Expected: All remaining tests PASS (the deleted test file is gone).

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove old single-file example, replaced by example/ project"
```

---

## Task 13: Set Up Sphinx Documentation

**Files:**
- Create: `docs/conf.py`
- Create: `docs/Makefile`
- Create: `docs/requirements.txt`
- Create: `.readthedocs.yml`
- Modify: `pyproject.toml` (add docs dependencies)

**Step 1: Create `docs/conf.py`**

```python
"""Sphinx configuration for django-sendparcel."""

project = "django-sendparcel"
copyright = "2026, Dominik Kozaczko"
author = "Dominik Kozaczko"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "plans"]

html_theme = "furo"
html_static_path = ["_static"]

autodoc_member_order = "bysource"
autodoc_typehints = "description"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "django": (
        "https://docs.djangoproject.com/en/5.2/",
        "https://docs.djangoproject.com/en/5.2/_objects/",
    ),
}

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
```

**Step 2: Create `docs/Makefile`**

```makefile
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
```

**Step 3: Create `docs/requirements.txt`**

```
furo
myst-parser
sphinx>=7.0
sphinx-autodoc-typehints
```

**Step 4: Create `.readthedocs.yml`**

```yaml
version: 2

build:
  os: ubuntu-22.04
  tools:
    python: "3.12"

sphinx:
  configuration: docs/conf.py

python:
  install:
    - requirements: docs/requirements.txt
    - method: pip
      path: .
```

**Step 5: Add docs optional dependencies to `pyproject.toml`**

Add to `[project.optional-dependencies]`:

```toml
docs = [
    "furo",
    "myst-parser",
    "sphinx>=7.0",
    "sphinx-autodoc-typehints",
]
```

**Step 6: Verify Sphinx builds**

Run: `uv run --extra docs sphinx-build -b html docs/ docs/_build/html`
Expected: Build completes with only the `index.md` page. Warnings about missing toctree entries are fine for now.

**Step 7: Commit**

```bash
git add docs/conf.py docs/Makefile docs/requirements.txt .readthedocs.yml pyproject.toml
git commit -m "docs: set up Sphinx with furo theme, myst-parser, and autodoc"
```

---

## Task 14: Write Quickstart Documentation

**Files:**
- Modify: `docs/index.md`
- Create: `docs/quickstart.md`

**Step 1: Update `docs/index.md` with toctree**

```markdown
# django-sendparcel

Adapter Django dla biblioteki [python-sendparcel](https://github.com/example/python-sendparcel) — zarządzanie przesyłkami kurierskimi w projektach Django.

## Spis treści

```{toctree}
:maxdepth: 2

quickstart
configuration
api
```
```

**Step 2: Create `docs/quickstart.md`**

```markdown
# Quickstart

## Installation

Install `django-sendparcel` using pip:

```bash
pip install django-sendparcel
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add django-sendparcel
```

## Django Configuration

### 1. Add to INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    "sendparcel_django",
    # your apps that define Order/Shipment models
    "myapp",
]
```

### 2. Configure the Shipment Model

Point `SENDPARCEL_SHIPMENT_MODEL` to your concrete Shipment model:

```python
SENDPARCEL_SHIPMENT_MODEL = "myapp.Shipment"
```

### 3. Create Your Models

Your app needs an Order model and a Shipment model that inherit from the library's abstract mixins:

```python
from django.db import models
from sendparcel_django.models import OrderModelMixin, ShipmentModelMixin


class Order(OrderModelMixin):
    description = models.CharField(max_length=255)
    recipient_name = models.CharField(max_length=128)
    recipient_email = models.EmailField()
    recipient_phone = models.CharField(max_length=32)
    recipient_line1 = models.CharField(max_length=255)
    recipient_city = models.CharField(max_length=128)
    recipient_postal_code = models.CharField(max_length=16)

    def get_total_weight(self):
        return Decimal("1.0")

    def get_parcels(self):
        return [{"weight_kg": self.get_total_weight()}]

    def get_sender_address(self):
        return {
            "name": "My Warehouse",
            "line1": "ul. Magazynowa 1",
            "city": "Warszawa",
            "postal_code": "00-001",
            "country_code": "PL",
        }

    def get_receiver_address(self):
        return {
            "name": self.recipient_name,
            "line1": self.recipient_line1,
            "city": self.recipient_city,
            "postal_code": self.recipient_postal_code,
            "country_code": "PL",
            "email": self.recipient_email,
            "phone": self.recipient_phone,
        }


class Shipment(ShipmentModelMixin):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="shipments"
    )
```

### 4. Configure Provider Settings

```python
SENDPARCEL_PROVIDER_SETTINGS = {
    "dummy": {
        "label_base_url": "https://dummy.local/labels",
        "callback_token": "your-secret-token",
    },
}
```

### 5. Include URL Patterns

```python
from django.urls import include, path

urlpatterns = [
    # ...
    path("sendparcel/", include("sendparcel_django.urls")),
]
```

### 6. Run Migrations

```bash
python manage.py makemigrations myapp
python manage.py migrate
```

## Creating a Shipment

Use `ShipmentFlow` to create shipments through the core sendparcel pipeline:

```python
import anyio
from sendparcel.flow import ShipmentFlow
from sendparcel_django.protocols import DjangoOrderAdapter
from sendparcel_django.repository import DjangoShipmentRepository

repository = DjangoShipmentRepository()
flow = ShipmentFlow(repository=repository, config=settings.SENDPARCEL_PROVIDER_SETTINGS)

order = Order.objects.get(pk=1)
adapted_order = DjangoOrderAdapter(wrapped=order)

# In a sync Django view, use anyio.run():
shipment = anyio.run(flow.create_shipment, adapted_order, "dummy")
```

## Handling Callbacks

The library provides a callback endpoint at `/sendparcel/callback/<shipment_id>/`. Providers send HTTP POST requests to this endpoint to notify status changes.

## Example Project

See the `example/` directory in the repository for a complete working Django project with:

- Concrete Order and Shipment models
- Tabler UI templates with HTMX
- A delivery simulator that sends callbacks
- Django admin integration

Run it with:

```bash
cd example/
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
```

**Step 3: Commit**

```bash
git add docs/index.md docs/quickstart.md
git commit -m "docs: add quickstart guide with installation and usage examples"
```

---

## Task 15: Write Configuration Reference

**Files:**
- Create: `docs/configuration.md`

**Step 1: Create `docs/configuration.md`**

```markdown
# Configuration Reference

All settings are defined in your Django `settings.py`.

## SENDPARCEL_SHIPMENT_MODEL

**Required.** The dotted path to your concrete Shipment model (similar to Django's `AUTH_USER_MODEL`).

```python
SENDPARCEL_SHIPMENT_MODEL = "myapp.Shipment"
```

Your model must inherit from `sendparcel_django.models.ShipmentModelMixin` and include a ForeignKey to your Order model.

## SENDPARCEL_PROVIDER_SETTINGS

**Optional.** A dictionary of provider-specific configuration. Keys are provider slugs, values are config dicts passed to the provider's constructor.

```python
SENDPARCEL_PROVIDER_SETTINGS = {
    "dummy": {
        "label_base_url": "https://labels.example.com",
        "callback_token": "secret-token",
        "latency_seconds": 0.1,
    },
    "inpost": {
        "api_key": "your-api-key",
        "api_url": "https://api.inpost.pl/v1",
        "callback_token": "inpost-webhook-secret",
    },
}
```

Each provider reads its own settings via `self.get_setting(name, default)` in its `BaseProvider` subclass.

## SENDPARCEL_DEFAULT_PROVIDER

**Optional.** The default provider slug used when no provider is explicitly specified.

```python
SENDPARCEL_DEFAULT_PROVIDER = "dummy"
```

## Swappable Models

### OrderModelMixin

Abstract Django model that your Order model must inherit from. It defines the contract:

| Method | Return type | Description |
|--------|-------------|-------------|
| `get_total_weight()` | `Decimal` | Total weight of all parcels |
| `get_parcels()` | `list[dict]` | List of parcel info dicts |
| `get_sender_address()` | `dict` | Sender address fields |
| `get_receiver_address()` | `dict` | Receiver address fields |

### ShipmentModelMixin

Abstract Django model providing shipment fields:

| Field | Type | Description |
|-------|------|-------------|
| `provider` | `CharField(64)` | Provider slug |
| `status` | `CharField(32)` | Current FSM status |
| `external_id` | `CharField(128)` | Provider's shipment ID |
| `tracking_number` | `CharField(128)` | Tracking number |
| `label_url` | `URLField` | Label download URL |

## Provider Registration

Providers are registered automatically via Python entry points or manually in your app's `ready()` method:

```python
# myapp/apps.py
from django.apps import AppConfig


class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        from sendparcel_django.registry import registry
        from myapp.providers import MyProvider

        registry.register(MyProvider)
```

### Entry Point Registration

Add to your package's `pyproject.toml`:

```toml
[project.entry-points."sendparcel.providers"]
myprovider = "mypackage.provider:MyProvider"
```

## Middleware

### SendParcelExceptionMiddleware

Maps sendparcel exceptions to HTTP responses in views:

| Exception | HTTP Status |
|-----------|-------------|
| `InvalidCallbackError` | 400 Bad Request |
| `InvalidTransitionError` | 409 Conflict |
| `CommunicationError` | 502 Bad Gateway |
| `SendParcelException` | 400 Bad Request |

Add to `MIDDLEWARE`:

```python
MIDDLEWARE = [
    # ...
    "sendparcel_django.middleware.SendParcelExceptionMiddleware",
]
```

## Template Tags

Load the `sendparcel` template tags library:

```html
{% load sendparcel %}
```

Available tags:

| Tag | Description |
|-----|-------------|
| `{% shipment_status_badge shipment %}` | Renders a colored status badge |
| `{% provider_choices as providers %}` | Loads provider choices into template variable |
```

**Step 2: Commit**

```bash
git add docs/configuration.md
git commit -m "docs: add configuration reference with all settings and middleware"
```

---

## Task 16: Write API Documentation

**Files:**
- Create: `docs/api.md`

**Step 1: Create `docs/api.md`**

```markdown
# API Reference

## Models

```{eval-rst}
.. automodule:: sendparcel_django.models
   :members:
   :undoc-members:
   :show-inheritance:
```

## Protocols

```{eval-rst}
.. automodule:: sendparcel_django.protocols
   :members:
   :undoc-members:
   :show-inheritance:
```

## Repository

```{eval-rst}
.. automodule:: sendparcel_django.repository
   :members:
   :undoc-members:
   :show-inheritance:
```

## Registry

```{eval-rst}
.. automodule:: sendparcel_django.registry
   :members:
   :undoc-members:
   :show-inheritance:
```

## Forms

```{eval-rst}
.. automodule:: sendparcel_django.forms
   :members:
   :undoc-members:
   :show-inheritance:
```

## Views

```{eval-rst}
.. automodule:: sendparcel_django.views
   :members:
   :undoc-members:
   :show-inheritance:
```

## Admin

```{eval-rst}
.. automodule:: sendparcel_django.admin
   :members:
   :undoc-members:
   :show-inheritance:
```

## Middleware

```{eval-rst}
.. automodule:: sendparcel_django.middleware
   :members:
   :undoc-members:
   :show-inheritance:
```

## URL Configuration

```{eval-rst}
.. automodule:: sendparcel_django.urls
   :members:
   :undoc-members:
```
```

**Step 2: Verify Sphinx builds with all documentation pages**

Run: `uv run --extra docs sphinx-build -b html docs/ docs/_build/html`
Expected: Build completes. Autodoc may warn about missing modules (e.g., `repository`, `middleware`) if foundation/features plans haven't been executed in this environment, but the structure is correct.

**Step 3: Add `docs/_build/` and `docs/_static/` to `.gitignore`**

Append to `.gitignore`:

```
docs/_build/
docs/_static/
```

**Step 4: Commit**

```bash
git add docs/api.md .gitignore
git commit -m "docs: add API reference with autodoc for all modules"
```

---

## Summary of Changes

| Task | Files | What |
|------|-------|------|
| 1 | `example/` skeleton | Project structure: manage.py, settings, URLs, app configs |
| 2 | `example/shipping/models.py` | Order and Shipment concrete models |
| 3 | `example/delivery_sim/provider.py` | Fake delivery provider (BaseProvider subclass) |
| 4 | `example/delivery_sim/views.py`, `urls.py` | Simulator dashboard and callback trigger |
| 5 | `example/templates/base.html` | Tabler base template with Polish navigation |
| 6 | `example/shipping/forms.py` | OrderForm and CreateShipmentForm |
| 7 | `example/shipping/views.py` | Order list/detail/create, shipment create/detail/tracking |
| 8 | `example/shipping/urls.py`, `admin.py` | URL routing and admin registration |
| 9 | `example/templates/shipping/` | 5 templates: list, create, detail, shipment detail, tracking partial |
| 10 | `example/templates/delivery_sim/` | Simulator gateway template |
| 11 | `example/delivery_sim/apps.py`, migrations | Provider registration, DB migrations |
| 12 | Remove `examples/`, update `pyproject.toml` | Delete old single-file example |
| 13 | `docs/conf.py`, `.readthedocs.yml`, `pyproject.toml` | Sphinx setup with furo + myst-parser |
| 14 | `docs/index.md`, `docs/quickstart.md` | Quickstart guide |
| 15 | `docs/configuration.md` | Configuration reference |
| 16 | `docs/api.md` | Autodoc API reference |

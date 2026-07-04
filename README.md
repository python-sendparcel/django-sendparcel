# django-sendparcel

[![PyPI](https://img.shields.io/pypi/v/django-sendparcel.svg)](https://pypi.org/project/django-sendparcel/)
[![Python Version](https://img.shields.io/pypi/pyversions/django-sendparcel.svg)](https://pypi.org/project/django-sendparcel/)
[![Django Version](https://img.shields.io/badge/django-%3E%3D5.2-blue.svg)](https://www.djangoproject.com/)
[![License](https://img.shields.io/pypi/l/django-sendparcel.svg)](https://github.com/python-sendparcel/django-sendparcel/blob/main/LICENSE)

Django adapter for the [python-sendparcel](https://github.com/python-sendparcel/python-sendparcel) multi-carrier shipping library.

> **Alpha (0.3.0)** — API may change between minor releases. Pin your dependency if you use it in production.

## Features

- **Shipment model with FSM** — built-in `Shipment` model with finite-state-machine transitions (new → created → label_ready → in_transit → delivered, etc.)
- **Swappable Shipment model** — replace the default `Shipment` with your own via `swapper`, similar to Django's `AUTH_USER_MODEL`
- **Django ORM repository** — `DjangoShipmentRepository` provides async-compatible persistence via `sync_to_async`; model instances satisfy the core `Shipment` protocol structurally (no adapter layer)
- **Provider plugin registry** — auto-discovers shipping provider plugins at app startup
- **Callback endpoint** — receives provider status webhooks and routes them through `ShipmentFlow`
- **Admin integration** — `ShipmentAdmin` with list filters, search, and bulk actions (mark in transit, mark delivered, cancel)
- **Exception middleware** — `SendParcelExceptionMiddleware` maps sendparcel exceptions to appropriate HTTP status codes
- **Provider choice form** — `ProviderChoiceForm` dynamically populated from the plugin registry
- **Callback retry persistence** — `CallbackRetry` model stores failed callback attempts for later reprocessing

## Installation

Install with pip (or your preferred package manager):

```bash
pip install django-sendparcel
```

This will also install the required dependencies: `python-sendparcel`, `Django`, `anyio`, and `swapper`.

## Quick Start

### 1. Add to INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    "sendparcel_django",
    # ...
]
```

### 2. Configure settings

```python
# Provider-specific configuration, keyed by provider slug
SENDPARCEL_PROVIDER_SETTINGS = {
    "my-provider": {
        "api_url": "https://api.example.com/",
        "api_key": "your-api-key",
    },
}

# Default provider slug (optional)
SENDPARCEL_DEFAULT_PROVIDER = "my-provider"

# Custom shipment model (optional, default: "sendparcel_django.Shipment")
# Uses django-swapper convention: <APP_LABEL>_<MODEL_NAME>
SENDPARCEL_DJANGO_SHIPMENT_MODEL = "myapp.Shipment"
```

### 3. (Optional) Create a custom Shipment model

If you need additional fields on the Shipment, extend `ShipmentModelMixin` and point the setting to your model:

```python
from django.db import models
from sendparcel_django.models import ShipmentModelMixin


class Shipment(ShipmentModelMixin):
    # Add custom fields as needed
    notes = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "shipment"
```

Then in settings:

```python
SENDPARCEL_DJANGO_SHIPMENT_MODEL = "myapp.Shipment"
```

### 4. Include URL configuration

```python
from django.urls import include, path

urlpatterns = [
    # ...
    path("sendparcel/", include("sendparcel_django.urls")),
]
```

This exposes the callback endpoint at `sendparcel/callback/<shipment_id>/` for receiving provider webhooks.

Successful callback responses include `provider`, `status`, `shipment`, and
`update`. The adapter no longer persists label URLs on shipment models.

> **Webhook security:** the callback endpoint is CSRF-exempt and performs
> no authentication of its own — authenticity checking is delegated
> entirely to the provider's `verify_callback` (e.g. InPost verifies the
> source IP). Only enable providers whose `verify_callback` performs real
> verification, or protect the endpoint at the web-server/proxy layer
> (IP allowlist, shared-secret path, mTLS).

### 5. (Optional) Add the exception middleware

```python
MIDDLEWARE = [
    # ...
    "sendparcel_django.middleware.SendParcelExceptionMiddleware",
]
```

This catches sendparcel exceptions and returns appropriate JSON error responses:

| Exception              | HTTP Status |
|------------------------|-------------|
| `CommunicationError`  | 502         |
| `ProviderNotFoundError` | 404       |
| `ProviderCapabilityError` | 409    |
| `InvalidCallbackError` | 400         |
| `InvalidTransitionError` | 409       |
| `SendParcelException` | 400         |

### 6. Run migrations

```bash
python manage.py migrate
```

## Usage

### Creating a shipment

Use `ShipmentFlow` to create shipments with explicit address and parcel data:

```python
import anyio
from sendparcel.flow import ShipmentFlow
from sendparcel_django.repository import DjangoShipmentRepository


async def create_shipment(provider_slug):
    repository = DjangoShipmentRepository()
    flow = ShipmentFlow(
        repository=repository,
        config=settings.SENDPARCEL_PROVIDER_SETTINGS,
    )

    outcome = await flow.create_shipment(
        provider_slug,
        sender_address={
            "name": "My Warehouse",
            "line1": "1 Warehouse St",
            "city": "Warsaw",
            "postal_code": "00-001",
            "country_code": "PL",
        },
        receiver_address={
            "name": "Customer Name",
            "line1": "10 Customer Ave",
            "city": "Krakow",
            "postal_code": "30-001",
            "country_code": "PL",
        },
        parcels=[{"weight_kg": 2.5}],
        reference_id="my-order-123",  # optional reference for your system
    )

    shipment = outcome.shipment
    if outcome.label is None:
        label_outcome = await flow.create_label(shipment)
        return label_outcome.shipment

    return shipment
```

Call from synchronous Django code using `anyio.run()`:

```python
shipment = anyio.run(create_shipment, "my-provider")
```

### Provider choice form

Use `ProviderChoiceForm` to let users select a shipping provider:

```python
from sendparcel_django.forms import ProviderChoiceForm

form = ProviderChoiceForm(request.POST)
if form.is_valid():
    provider_slug = form.cleaned_data["provider"]
```

The form choices are dynamically populated from the plugin registry.

### Admin

The `ShipmentAdmin` is auto-registered for the active Shipment model (default or swapped). It provides:

- **List display**: ID, reference ID, status, provider, tracking number, creation date
- **Filters**: status, provider
- **Search**: tracking number, external ID, reference ID
- **Bulk actions**: mark as in transit, mark as delivered, cancel — each action triggers FSM transitions with guard validation

## Configuration Reference

All settings are read from your Django settings module.

| Setting                        | Type   | Default                       | Description                                           |
|--------------------------------|--------|-------------------------------|-------------------------------------------------------|
| `SENDPARCEL_PROVIDER_SETTINGS` | `dict` | `{}`                          | Provider-specific configuration, keyed by provider slug |
| `SENDPARCEL_DEFAULT_PROVIDER`  | `str`  | `""`                          | Default provider slug                                  |
| `SENDPARCEL_DJANGO_SHIPMENT_MODEL` | `str`  | `"sendparcel_django.Shipment"` | Dotted path to the Shipment model (swappable via `django-swapper`) |

Settings are resolved at call time via `sendparcel_django.conf.get_settings()`, so `@override_settings` works correctly in tests.

## Shipment Model Fields

The `ShipmentModelMixin` provides these fields on every Shipment (default or custom):

| Field             | Type         | Description                          |
|-------------------|--------------|--------------------------------------|
| `reference_id`    | `CharField`  | Your system's reference (e.g. order ID) |
| `provider`        | `CharField`  | Provider slug                        |
| `status`          | `CharField`  | Current FSM state (default: `"new"`) |
| `external_id`     | `CharField`  | Provider-assigned shipment ID        |
| `tracking_number` | `CharField`  | Tracking number from provider        |
| `created_at`      | `DateTimeField` | Auto-set on creation              |
| `updated_at`      | `DateTimeField` | Auto-set on save                  |

The default concrete `Shipment` model uses these fields directly. When creating a custom model, you can add any additional fields you need.

## Example Project

A full working example is included in the `example/` directory. It demonstrates:

- A custom `Shipment` model with inline address fields
- Shipment creation through the `ShipmentFlow`
- A delivery simulation provider for local testing
- HTMX-powered shipment tracking UI

To run the example:

```bash
cd example
pip install -e ..
pip install -e ../../python-sendparcel
python manage.py migrate
python manage.py runserver
```

## Supported Versions

| Dependency | Version    |
|------------|------------|
| Python     | >= 3.12    |
| Django     | >= 5.2     |
| python-sendparcel | >= 0.1.1 |
| anyio      | >= 4.0     |
| swapper    | >= 1.4     |

## Running Tests

The test suite uses `pytest` with `pytest-django`:

```bash
pip install -e ".[dev]"
pytest
```

Test configuration is in `tests/settings.py`. The test suite covers models, protocols, views, middleware, admin, forms, registry, repository, FSM integration, and callback retry logic.

## Credits

- **Author**: Dominik Kozaczko ([dominik@kozaczko.info](mailto:dominik@kozaczko.info))
- Built on top of [python-sendparcel](https://github.com/python-sendparcel/python-sendparcel) core library
- Model swapping powered by [django-swapper](https://github.com/openwisp/django-swapper)

## License

MIT License. See [LICENSE](https://github.com/python-sendparcel/django-sendparcel/blob/main/LICENSE) for details.

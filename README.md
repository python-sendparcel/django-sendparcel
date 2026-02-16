# django-sendparcel

[![PyPI](https://img.shields.io/pypi/v/django-sendparcel.svg)](https://pypi.org/project/django-sendparcel/)
[![Python Version](https://img.shields.io/pypi/pyversions/django-sendparcel.svg)](https://pypi.org/project/django-sendparcel/)
[![Django Version](https://img.shields.io/badge/django-%3E%3D5.2-blue.svg)](https://www.djangoproject.com/)
[![License](https://img.shields.io/pypi/l/django-sendparcel.svg)](https://github.com/sendparcel/django-sendparcel/blob/main/LICENSE)

Django adapter for the [python-sendparcel](https://github.com/sendparcel/python-sendparcel) multi-carrier shipping library.

> **Alpha (0.1.0)** — API may change between minor releases. Pin your dependency if you use it in production.

## Features

- **Shipment model with FSM** — built-in `Shipment` model with finite-state-machine transitions (new → created → label_ready → in_transit → delivered, etc.)
- **Swappable Shipment model** — replace the default `Shipment` with your own via `swapper`, similar to Django's `AUTH_USER_MODEL`
- **Order model mixin** — `OrderModelMixin` defines the contract your Order model must satisfy (weight, parcels, addresses)
- **Protocol adapters** — `DjangoOrderAdapter` and `DjangoShipmentAdapter` bridge Django models to the framework-agnostic core
- **Django ORM repository** — `DjangoShipmentRepository` provides async-compatible persistence via `sync_to_async`
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

### 3. Create your Order model

Your Order model must extend `OrderModelMixin` and implement four methods:

```python
from decimal import Decimal
from django.db import models
from sendparcel_django.models import OrderModelMixin


class Order(OrderModelMixin):
    description = models.CharField(max_length=255)
    recipient_name = models.CharField(max_length=128)
    recipient_line1 = models.CharField(max_length=255)
    recipient_city = models.CharField(max_length=128)
    recipient_postal_code = models.CharField(max_length=16)

    def get_total_weight(self) -> Decimal:
        return Decimal("2.5")

    def get_parcels(self) -> list[dict]:
        return [{"weight_kg": self.get_total_weight()}]

    def get_sender_address(self) -> dict:
        return {
            "name": "My Warehouse",
            "line1": "1 Warehouse St",
            "city": "Warsaw",
            "postal_code": "00-001",
            "country_code": "PL",
        }

    def get_receiver_address(self) -> dict:
        return {
            "name": self.recipient_name,
            "line1": self.recipient_line1,
            "city": self.recipient_city,
            "postal_code": self.recipient_postal_code,
            "country_code": "PL",
        }
```

### 4. (Optional) Create a custom Shipment model

If you need additional fields on the Shipment, extend `ShipmentModelMixin` and point the setting to your model:

```python
from django.db import models
from sendparcel_django.models import ShipmentModelMixin


class Shipment(ShipmentModelMixin):
    order = models.ForeignKey(
        "myapp.Order",
        on_delete=models.CASCADE,
        related_name="shipments",
    )

    class Meta:
        verbose_name = "shipment"
```

Then in settings:

```python
SENDPARCEL_DJANGO_SHIPMENT_MODEL = "myapp.Shipment"
```

### 5. Include URL configuration

```python
from django.urls import include, path

urlpatterns = [
    # ...
    path("sendparcel/", include("sendparcel_django.urls")),
]
```

This exposes the callback endpoint at `sendparcel/callback/<shipment_id>/` for receiving provider webhooks.

### 6. (Optional) Add the exception middleware

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
| `InvalidCallbackError` | 400         |
| `InvalidTransitionError` | 409       |
| `SendParcelException` | 400         |

### 7. Run migrations

```bash
python manage.py migrate
```

## Usage

### Creating a shipment

Use `DjangoOrderAdapter` to bridge your Django Order model to the core `ShipmentFlow`:

```python
import anyio
from sendparcel.flow import ShipmentFlow
from sendparcel_django.protocols import DjangoOrderAdapter
from sendparcel_django.repository import DjangoShipmentRepository


async def create_shipment_for_order(order, provider_slug):
    repository = DjangoShipmentRepository()
    flow = ShipmentFlow(
        repository=repository,
        config=settings.SENDPARCEL_PROVIDER_SETTINGS,
    )

    adapted_order = DjangoOrderAdapter(wrapped=order)
    shipment = await flow.create_shipment(adapted_order, provider_slug)

    # Generate a label if the provider supports it
    if not shipment.label_url:
        shipment = await flow.create_label(shipment)

    return shipment
```

Call from synchronous Django code using `anyio.run()`:

```python
shipment = anyio.run(create_shipment_for_order, order, "my-provider")
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

- **List display**: ID, order ID, status, provider, tracking number, label URL, creation date
- **Filters**: status, provider
- **Search**: tracking number, external ID, order ID
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
| `provider`        | `CharField`  | Provider slug                        |
| `status`          | `CharField`  | Current FSM state (default: `"new"`) |
| `external_id`     | `CharField`  | Provider-assigned shipment ID        |
| `tracking_number` | `CharField`  | Tracking number from provider        |
| `label_url`       | `URLField`   | URL to the shipping label            |
| `created_at`      | `DateTimeField` | Auto-set on creation              |
| `updated_at`      | `DateTimeField` | Auto-set on save                  |

The default concrete `Shipment` model adds an `order_id` CharField. When creating a custom model, you can use a ForeignKey or any other relation to link shipments to orders.

## Example Project

A full working example is included in the `example/` directory. It demonstrates:

- An `Order` model with `OrderModelMixin`
- A custom `Shipment` model with a ForeignKey to Order
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
| python-sendparcel | >= 0.1.0 |
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
- Built on top of [python-sendparcel](https://github.com/sendparcel/python-sendparcel) core library
- Model swapping powered by [django-swapper](https://github.com/openwisp/django-swapper)

## License

MIT License. See [LICENSE](https://github.com/sendparcel/django-sendparcel/blob/main/LICENSE) for details.

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
    # your apps that define custom Shipment models (if any)
    "myapp",
]
```

### 2. Configure the Shipment Model (optional)

If you need a custom Shipment model, point `SENDPARCEL_SHIPMENT_MODEL` to it:

```python
SENDPARCEL_SHIPMENT_MODEL = "myapp.Shipment"
```

### 3. (Optional) Create a Custom Shipment Model

If you need additional fields, extend `ShipmentModelMixin`:

```python
from django.db import models
from sendparcel_django.models import ShipmentModelMixin


class Shipment(ShipmentModelMixin):
    notes = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "shipment"
```

The built-in `ShipmentModelMixin` already provides `reference_id`, `provider`, `status`, `external_id`, `tracking_number`, `created_at`, and `updated_at` fields.

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
python manage.py makemigrations myapp  # only if using a custom Shipment model
python manage.py migrate
```

## Creating a Shipment

Use `ShipmentFlow` to create shipments with explicit address and parcel data:

```python
import anyio
from django.conf import settings
from sendparcel.flow import ShipmentFlow
from sendparcel_django.repository import DjangoShipmentRepository

repository = DjangoShipmentRepository()
flow = ShipmentFlow(repository=repository, config=settings.SENDPARCEL_PROVIDER_SETTINGS)

# In a sync Django view, use anyio.run():
outcome = anyio.run(
    flow.create_shipment,
    "dummy",
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
    reference_id="my-order-123",
)

shipment = outcome.shipment
label = outcome.label
```

Providers may return the label inline during shipment creation. If `outcome.label`
is `None`, call `flow.create_label(shipment)` and use the returned
`CreateLabelOutcome`.

## Handling Callbacks

The library provides a built-in callback view at `/sendparcel/callback/<shipment_id>/`. Providers send HTTP POST requests to this endpoint to notify status changes.

The view is decorated with `@csrf_exempt` and `@require_POST` and handles repository instantiation automatically.

Successful callback responses return JSON with:

- `provider`
- `status` set to `"accepted"`
- `shipment` containing the persisted shipment snapshot
- `update` containing the normalized provider update payload

If you need to use a custom view, you can import and use the `callback` view as a base or reference:

```python
from django.urls import path
from sendparcel_django.views import callback

# Example of manual view wiring
urlpatterns = [
    path("my-callback/<str:shipment_id>/", callback, name="custom-callback"),
]
```

## Example Project

See the `example/` directory in the repository for a complete working Django project with:

- A Shipment model with inline address fields
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

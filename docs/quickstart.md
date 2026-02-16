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

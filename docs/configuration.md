# Configuration Reference

All settings are defined in your Django `settings.py`.

## SENDPARCEL_DJANGO_SHIPMENT_MODEL

**Optional.** The dotted path to your concrete Shipment model (similar to Django's `AUTH_USER_MODEL`). Defaults to `"sendparcel_django.Shipment"`.

```python
SENDPARCEL_DJANGO_SHIPMENT_MODEL = "myapp.Shipment"
```

Your model must inherit from `sendparcel_django.models.ShipmentModelMixin`.

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

### ShipmentModelMixin

Abstract Django model providing shipment fields:

| Field | Type | Description |
|-------|------|-------------|
| `reference_id` | `CharField(255)` | Your system's reference (e.g. order ID) |
| `provider` | `CharField(64)` | Provider slug |
| `status` | `CharField(32)` | Current FSM status |
| `external_id` | `CharField(128)` | Provider's shipment ID |
| `tracking_number` | `CharField(128)` | Tracking number |
| `created_at` | `DateTimeField` | Auto-set on creation |
| `updated_at` | `DateTimeField` | Auto-set on save |

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

| Exception | HTTP Status | Description |
|-----------|-------------|-------------|
| `ShipmentNotFoundError` | 404 Not Found | Shipment ID does not exist |
| `ProviderNotFoundError` | 404 Not Found | Shipment provider is not registered |
| `ProviderCapabilityError` | 409 Conflict | Provider does not support requested capability |
| `InvalidCallbackError` | 400 Bad Request | Invalid callback payload or token |
| `InvalidTransitionError` | 409 Conflict | Shipment status transition not allowed |
| `CommunicationError` | 502 Bad Gateway | Provider API communication failure |
| `SendParcelException` | 400 Bad Request | Other library errors |

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

## Protocols

### CallbackRetryStore

Storage abstraction for the webhook retry queue. Note that the Django implementation is synchronous due to framework constraints.

```python
from typing import Any, Protocol

class CallbackRetryStore(Protocol):
    def store_failed_callback(
        self,
        shipment_id: str,
        provider_slug: str,
        payload: dict[str, Any],
        headers: dict[str, Any],
    ) -> str:
        """Store a failed callback for later retry. Returns retry ID."""
        ...

    def get_due_retries(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get retries that are due for processing."""
        ...

    def mark_succeeded(self, retry_id: str) -> None:
        """Mark a retry as successfully processed."""
        ...

    def mark_failed(self, retry_id: str, error: str) -> None:
        """Mark a retry as failed and schedule next attempt."""
        ...

    def mark_exhausted(self, retry_id: str) -> None:
        """Mark a retry as exhausted (dead letter)."""
        ...
```

The library provides a default implementation using the Django ORM: `sendparcel_django.retry.DjangoCallbackRetryStore`.

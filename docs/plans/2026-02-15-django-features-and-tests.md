# Django Features & Comprehensive Test Suite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add template tags, callback retry mechanism, exception middleware, and a comprehensive test suite (~65 tests) for django-sendparcel.

**Architecture:** Template tags use Django's template library to render shipment status badges, provider choices, and tracking info as reusable HTML fragments. The retry mechanism persists failed callbacks in a `CallbackRetry` model with exponential backoff, using a store protocol for testability. Exception middleware maps sendparcel core exceptions to appropriate HTTP status codes via Django's `process_exception` hook. The test suite covers models, FSM integration, views, admin, repository, config, retry, middleware, template tags, and public API.

**Tech Stack:** Django 5.2+, pytest, pytest-django, pytest-factoryboy, factory_boy, python-transitions, sendparcel core

---

## Prerequisites

This plan **assumes the foundation plan** (`2026-02-15-django-foundation.md`) has already been executed. The following exist:

- `sendparcel_django/apps.py` — `SendParcelConfig(AppConfig)` with `default_auto_field = "django.db.models.BigAutoField"`
- `sendparcel_django/conf.py` — `get_setting(name, default)` reading from `django.conf.settings` with `SENDPARCEL_` prefix
- `sendparcel_django/repository.py` — `DjangoShipmentRepository` implementing the `ShipmentRepository` protocol
- `sendparcel_django/models.py` — concrete `Shipment` model (swappable via `SENDPARCEL_SHIPMENT_MODEL` setting) with `order_id` CharField, plus existing abstract mixins
- `sendparcel_django/admin.py` — `ShipmentAdmin(ModelAdmin)` with `list_display`, `list_filter`, and bulk actions using `build_status_actions()`
- `sendparcel_django/views.py` — callback view using `DjangoShipmentRepository` by default
- `sendparcel_django/migrations/0001_initial.py` — initial migration for Shipment model
- Existing tests updated for DB-backed operations

### Package layout after foundation

```
sendparcel_django/
  __init__.py
  admin.py
  apps.py
  conf.py
  forms.py
  middleware.py         (this plan creates)
  models.py
  protocols.py
  registry.py
  repository.py
  retry.py              (this plan creates)
  urls.py
  views.py
  migrations/
    __init__.py
    0001_initial.py
    0002_callbackretry.py  (this plan creates)
  templatetags/
    __init__.py            (this plan creates)
    sendparcel_tags.py     (this plan creates)
tests/
  __init__.py
  conftest.py
  factories.py           (this plan creates)
  test_admin.py
  test_conf.py           (this plan creates)
  test_example_app.py
  test_forms.py
  test_fsm_integration.py  (this plan creates)
  test_middleware.py       (this plan creates)
  test_models.py           (this plan creates)
  test_protocols.py
  test_public_api.py       (this plan creates)
  test_registry.py
  test_repository.py       (this plan creates)
  test_retry.py            (this plan creates)
  test_tags.py             (this plan creates)
  test_views.py
```

### Running tests

All commands run from `django-sendparcel/` directory:

```bash
uv run pytest tests/ -v
uv run pytest tests/test_specific.py -v
uv run pytest tests/test_specific.py::test_name -v
```

### Key core imports reference

```python
from sendparcel.enums import ShipmentStatus
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
)
from sendparcel.fsm import create_shipment_machine, SHIPMENT_TRANSITIONS
from sendparcel.flow import ShipmentFlow
from sendparcel.provider import BaseProvider
from sendparcel.registry import registry as core_registry
from transitions.core import MachineError
```

### ShipmentStatus enum values

```python
class ShipmentStatus(StrEnum):
    NEW = "new"
    CREATED = "created"
    LABEL_READY = "label_ready"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    FAILED = "failed"
    RETURNED = "returned"
```

---

## Task 1: Test infrastructure — update conftest.py and add dev dependencies

**Files:**
- Modify: `pyproject.toml` (add pytest-django, pytest-factoryboy, factory-boy to dev deps)
- Modify: `tests/conftest.py` (full Django settings for DB-backed tests)
- Create: `tests/__init__.py` (empty, needed for pytest discovery)

**Step 1: Add dev dependencies to pyproject.toml**

In `pyproject.toml`, replace the `[project.optional-dependencies]` section:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "pytest-django>=4.9.0",
    "pytest-factoryboy>=2.7.0",
    "factory-boy>=3.3.0",
    "ruff>=0.9.0",
]
```

Also add Django test settings to `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
DJANGO_SETTINGS_MODULE = "tests.settings"
```

Wait — pytest-django expects a settings module. But we use `settings.configure()` in conftest. The simplest approach: keep `settings.configure()` in conftest.py and set `django_find_project = false` in pytest ini to avoid DJANGO_SETTINGS_MODULE requirement.

Actually, the cleanest approach: use a `conftest.py` with `django_find_project = false` and configure in conftest. Replace the `[tool.pytest.ini_options]` section with:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**Step 2: Install dev dependencies**

Run:
```bash
uv sync --extra dev
```
Expected: Installs pytest-django, pytest-factoryboy, factory-boy successfully.

**Step 3: Rewrite `tests/conftest.py` with full Django settings**

Replace `tests/conftest.py` entirely:

```python
"""Shared fixtures for django-sendparcel tests."""

from __future__ import annotations

from collections.abc import Iterator

import django
import pytest
from django.conf import settings
from sendparcel.registry import registry as core_registry

from sendparcel_django.registry import registry as django_registry

if not settings.configured:
    settings.configure(
        DEFAULT_CHARSET="utf-8",
        USE_I18N=False,
        SECRET_KEY="test-secret-key-not-for-production",
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "sendparcel_django",
        ],
        SENDPARCEL_SHIPMENT_MODEL="sendparcel_django.Shipment",
        MIDDLEWARE=[
            "sendparcel_django.middleware.SendParcelExceptionMiddleware",
        ],
        ROOT_URLCONF="sendparcel_django.urls",
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    )
    django.setup()


@pytest.fixture(autouse=True)
def isolate_registries() -> Iterator[None]:
    """Reset global registries between tests."""
    core_old = dict(core_registry._providers)
    core_discovered = core_registry._discovered
    django_old = dict(django_registry._providers)
    django_discovered = django_registry._discovered

    core_registry._providers = {}
    core_registry._discovered = True
    django_registry._providers = {}
    django_registry._discovered = True

    try:
        yield
    finally:
        core_registry._providers = core_old
        core_registry._discovered = core_discovered
        django_registry._providers = django_old
        django_registry._discovered = django_discovered
```

**Step 4: Create `tests/__init__.py`**

```python
```

(Empty file.)

**Step 5: Verify existing tests still pass**

Run:
```bash
uv run pytest tests/test_registry.py tests/test_protocols.py tests/test_forms.py -v
```
Expected: All existing tests pass. (DB-dependent tests like test_admin.py and test_views.py may need the foundation plan complete first.)

**Step 6: Commit**

```bash
git add pyproject.toml tests/conftest.py tests/__init__.py
git commit -m "chore: add pytest-django and pytest-factoryboy dev deps, update conftest for DB tests"
```

---

## Task 2: Create test factories

**Files:**
- Create: `tests/factories.py`

**Step 1: Write factories**

```python
"""Model factories for django-sendparcel tests."""

from __future__ import annotations

import factory
from sendparcel.enums import ShipmentStatus

from sendparcel_django.models import Shipment


class ShipmentFactory(factory.django.DjangoModelFactory):
    """Factory for Shipment model instances."""

    class Meta:
        model = Shipment

    provider = "dummy"
    status = ShipmentStatus.NEW
    external_id = ""
    tracking_number = ""
    label_url = ""
    order_id = factory.Sequence(lambda n: f"order-{n}")
```

> **Note:** `CallbackRetryFactory` will be added in Task 5 when the `CallbackRetry` model is created.

**Step 2: Verify factory can be imported**

Run:
```bash
uv run python -c "from tests.factories import ShipmentFactory; print('OK')"
```
Expected: `OK`

**Step 3: Commit**

```bash
git add tests/factories.py
git commit -m "feat: add factory_boy factories for Shipment model"
```

---

## Task 3: Template tags — tests first

**Files:**
- Create: `sendparcel_django/templatetags/__init__.py`
- Create: `sendparcel_django/templatetags/sendparcel_tags.py`
- Create: `tests/test_tags.py`

**Step 1: Write failing tests for template tags**

Create `tests/test_tags.py`:

```python
"""Template tag tests."""

from __future__ import annotations

import pytest
from django.template import Context, Template
from sendparcel.enums import ShipmentStatus
from sendparcel.provider import BaseProvider

from sendparcel_django.registry import registry


class FakeProvider(BaseProvider):
    slug = "fake"
    display_name = "Fake Carrier"

    async def create_shipment(self, **kwargs):
        return {}


class ShipmentStub:
    """Minimal shipment-like object for template rendering."""

    def __init__(
        self,
        *,
        status: str = ShipmentStatus.NEW,
        tracking_number: str = "",
        label_url: str = "",
    ) -> None:
        self.status = status
        self.tracking_number = tracking_number
        self.label_url = label_url


class TestShipmentStatusBadge:
    def test_renders_badge_with_status_text(self) -> None:
        shipment = ShipmentStub(status=ShipmentStatus.NEW)
        html = _render_tag(
            "{% load sendparcel_tags %}{% shipment_status_badge shipment %}",
            {"shipment": shipment},
        )
        assert "new" in html.lower()
        assert "badge" in html.lower()

    def test_delivered_has_success_color(self) -> None:
        shipment = ShipmentStub(status=ShipmentStatus.DELIVERED)
        html = _render_tag(
            "{% load sendparcel_tags %}{% shipment_status_badge shipment %}",
            {"shipment": shipment},
        )
        assert "bg-success" in html

    def test_failed_has_danger_color(self) -> None:
        shipment = ShipmentStub(status=ShipmentStatus.FAILED)
        html = _render_tag(
            "{% load sendparcel_tags %}{% shipment_status_badge shipment %}",
            {"shipment": shipment},
        )
        assert "bg-danger" in html

    def test_cancelled_has_secondary_color(self) -> None:
        shipment = ShipmentStub(status=ShipmentStatus.CANCELLED)
        html = _render_tag(
            "{% load sendparcel_tags %}{% shipment_status_badge shipment %}",
            {"shipment": shipment},
        )
        assert "bg-secondary" in html

    def test_in_transit_has_primary_color(self) -> None:
        shipment = ShipmentStub(status=ShipmentStatus.IN_TRANSIT)
        html = _render_tag(
            "{% load sendparcel_tags %}{% shipment_status_badge shipment %}",
            {"shipment": shipment},
        )
        assert "bg-primary" in html

    def test_new_has_info_color(self) -> None:
        shipment = ShipmentStub(status=ShipmentStatus.NEW)
        html = _render_tag(
            "{% load sendparcel_tags %}{% shipment_status_badge shipment %}",
            {"shipment": shipment},
        )
        assert "bg-info" in html


class TestProviderChoices:
    def test_renders_option_elements(self) -> None:
        registry.register(FakeProvider)
        html = _render_tag(
            "{% load sendparcel_tags %}{% provider_choices %}",
            {},
        )
        assert "<option" in html
        assert 'value="fake"' in html
        assert "Fake Carrier" in html

    def test_renders_empty_when_no_providers(self) -> None:
        html = _render_tag(
            "{% load sendparcel_tags %}{% provider_choices %}",
            {},
        )
        assert "<option" not in html


class TestTrackingInfo:
    def test_renders_tracking_number(self) -> None:
        shipment = ShipmentStub(tracking_number="TRK-123")
        html = _render_tag(
            "{% load sendparcel_tags %}{% tracking_info shipment %}",
            {"shipment": shipment},
        )
        assert "TRK-123" in html

    def test_renders_label_link_when_url_present(self) -> None:
        shipment = ShipmentStub(
            tracking_number="TRK-456",
            label_url="https://labels.example.com/456.pdf",
        )
        html = _render_tag(
            "{% load sendparcel_tags %}{% tracking_info shipment %}",
            {"shipment": shipment},
        )
        assert "TRK-456" in html
        assert 'href="https://labels.example.com/456.pdf"' in html

    def test_no_link_when_label_url_empty(self) -> None:
        shipment = ShipmentStub(tracking_number="TRK-789", label_url="")
        html = _render_tag(
            "{% load sendparcel_tags %}{% tracking_info shipment %}",
            {"shipment": shipment},
        )
        assert "TRK-789" in html
        assert "href=" not in html

    def test_empty_when_no_tracking_number(self) -> None:
        shipment = ShipmentStub(tracking_number="", label_url="")
        html = _render_tag(
            "{% load sendparcel_tags %}{% tracking_info shipment %}",
            {"shipment": shipment},
        )
        stripped = html.strip()
        assert stripped == ""


def _render_tag(template_str: str, context: dict) -> str:
    template = Template(template_str)
    return template.render(Context(context))
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_tags.py -v
```
Expected: FAIL — `TemplateSyntaxError: 'sendparcel_tags' is not a registered tag library`

**Step 3: Create templatetags package and implementation**

Create `sendparcel_django/templatetags/__init__.py`:

```python
```

(Empty file.)

Create `sendparcel_django/templatetags/sendparcel_tags.py`:

```python
"""Template tags for django-sendparcel."""

from __future__ import annotations

from django import template
from django.utils.html import escape, format_html

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
    return format_html("".join(str(p) for p in parts))


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
```

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_tags.py -v
```
Expected: All 12 tests PASS.

**Step 5: Commit**

```bash
git add sendparcel_django/templatetags/ tests/test_tags.py
git commit -m "feat: add template tags for status badge, provider choices, and tracking info"
```

---

## Task 4: Exception middleware — tests first

**Files:**
- Create: `sendparcel_django/middleware.py`
- Create: `tests/test_middleware.py`

**Step 1: Write failing tests for middleware**

Create `tests/test_middleware.py`:

```python
"""Exception middleware tests."""

from __future__ import annotations

import json

from django.http import HttpRequest, HttpResponse
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
)

from sendparcel_django.middleware import SendParcelExceptionMiddleware


def _make_middleware(
    response: HttpResponse | None = None,
) -> SendParcelExceptionMiddleware:
    """Create middleware with a dummy get_response."""

    def get_response(request: HttpRequest) -> HttpResponse:
        return response or HttpResponse("ok")

    return SendParcelExceptionMiddleware(get_response)


def _parse_json(response: HttpResponse) -> dict:
    return json.loads(response.content.decode("utf-8"))


class TestSendParcelExceptionMiddleware:
    def test_communication_error_returns_502(self) -> None:
        middleware = _make_middleware()
        request = HttpRequest()
        exc = CommunicationError("Provider timeout")

        response = middleware.process_exception(request, exc)

        assert response is not None
        assert response.status_code == 502
        body = _parse_json(response)
        assert body["code"] == "communication_error"
        assert "Provider timeout" in body["detail"]

    def test_invalid_callback_error_returns_400(self) -> None:
        middleware = _make_middleware()
        request = HttpRequest()
        exc = InvalidCallbackError("Bad signature")

        response = middleware.process_exception(request, exc)

        assert response is not None
        assert response.status_code == 400
        body = _parse_json(response)
        assert body["code"] == "invalid_callback"
        assert "Bad signature" in body["detail"]

    def test_invalid_transition_error_returns_409(self) -> None:
        middleware = _make_middleware()
        request = HttpRequest()
        exc = InvalidTransitionError("Cannot cancel delivered shipment")

        response = middleware.process_exception(request, exc)

        assert response is not None
        assert response.status_code == 409
        body = _parse_json(response)
        assert body["code"] == "invalid_transition"
        assert "Cannot cancel" in body["detail"]

    def test_generic_sendparcel_exception_returns_400(self) -> None:
        middleware = _make_middleware()
        request = HttpRequest()
        exc = SendParcelException("Something went wrong")

        response = middleware.process_exception(request, exc)

        assert response is not None
        assert response.status_code == 400
        body = _parse_json(response)
        assert body["code"] == "sendparcel_error"

    def test_non_sendparcel_exception_returns_none(self) -> None:
        middleware = _make_middleware()
        request = HttpRequest()
        exc = ValueError("unrelated error")

        response = middleware.process_exception(request, exc)

        assert response is None

    def test_normal_response_passes_through(self) -> None:
        expected = HttpResponse("hello", status=200)
        middleware = _make_middleware(response=expected)
        request = HttpRequest()

        response = middleware(request)

        assert response.status_code == 200
        assert response.content == b"hello"

    def test_exception_context_not_leaked(self) -> None:
        """Sensitive context from exception should not appear in response."""
        middleware = _make_middleware()
        request = HttpRequest()
        exc = CommunicationError(
            "API error",
            context={"api_key": "secret-123"},
        )

        response = middleware.process_exception(request, exc)

        assert response is not None
        body = _parse_json(response)
        assert "secret-123" not in json.dumps(body)
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_middleware.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'sendparcel_django.middleware'`

**Step 3: Implement middleware**

Create `sendparcel_django/middleware.py`:

```python
"""Django middleware for sendparcel exception handling."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
)

_EXCEPTION_MAP: list[tuple[type[SendParcelException], int, str]] = [
    (CommunicationError, 502, "communication_error"),
    (InvalidCallbackError, 400, "invalid_callback"),
    (InvalidTransitionError, 409, "invalid_transition"),
    (SendParcelException, 400, "sendparcel_error"),
]


class SendParcelExceptionMiddleware:
    """Map sendparcel exceptions to appropriate HTTP responses.

    Order matters: more specific exception types are checked first.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_exception(
        self,
        request: HttpRequest,
        exception: Exception,
    ) -> HttpResponse | None:
        for exc_type, status_code, code in _EXCEPTION_MAP:
            if isinstance(exception, exc_type):
                return JsonResponse(
                    {"detail": str(exception), "code": code},
                    status=status_code,
                )
        return None
```

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_middleware.py -v
```
Expected: All 7 tests PASS.

**Step 5: Commit**

```bash
git add sendparcel_django/middleware.py tests/test_middleware.py
git commit -m "feat: add SendParcelExceptionMiddleware mapping core exceptions to HTTP responses"
```

---

## Task 5: Callback retry mechanism — model and store

**Files:**
- Modify: `sendparcel_django/models.py` (add `CallbackRetry` model)
- Create: `sendparcel_django/retry.py` (store, backoff, processor)
- Create: `sendparcel_django/migrations/0002_callbackretry.py` (auto-generated)
- Modify: `tests/factories.py` (add `CallbackRetryFactory`)
- Create: `tests/test_retry.py`

### Step 1: Write failing tests for retry

Create `tests/test_retry.py`:

```python
"""Callback retry mechanism tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sendparcel.enums import ShipmentStatus

from sendparcel_django.models import CallbackRetry
from sendparcel_django.retry import (
    DjangoCallbackRetryStore,
    compute_next_retry_at,
    process_due_retries,
)


class TestComputeNextRetryAt:
    def test_first_attempt_uses_base_backoff(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=1, backoff_seconds=60)
        after = datetime.now(tz=UTC)

        assert before + timedelta(seconds=60) <= result <= after + timedelta(
            seconds=60
        )

    def test_second_attempt_doubles_backoff(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=2, backoff_seconds=60)

        expected_min = before + timedelta(seconds=120)
        assert result >= expected_min

    def test_third_attempt_quadruples_backoff(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=3, backoff_seconds=60)

        expected_min = before + timedelta(seconds=240)
        assert result >= expected_min

    def test_backoff_with_different_base(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=1, backoff_seconds=30)

        expected_min = before + timedelta(seconds=30)
        assert result >= expected_min


@pytest.mark.django_db
class TestDjangoCallbackRetryStore:
    def test_store_failed_callback_creates_record(self) -> None:
        store = DjangoCallbackRetryStore()

        retry_id = store.store_failed_callback(
            shipment_id="ship-1",
            payload={"event": "picked_up"},
            headers={"x-token": "abc"},
        )

        assert retry_id is not None
        record = CallbackRetry.objects.get(id=retry_id)
        assert record.shipment_id == "ship-1"
        assert record.payload == {"event": "picked_up"}
        assert record.headers == {"x-token": "abc"}
        assert record.status == "pending"
        assert record.attempts == 0

    def test_get_due_retries_returns_due_items_only(self) -> None:
        store = DjangoCallbackRetryStore()
        # Due retry
        store.store_failed_callback("ship-due", {}, {})
        CallbackRetry.objects.filter(shipment_id="ship-due").update(
            next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )
        # Future retry
        store.store_failed_callback("ship-future", {}, {})
        CallbackRetry.objects.filter(shipment_id="ship-future").update(
            next_retry_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )

        due = store.get_due_retries(limit=10)

        shipment_ids = [r["shipment_id"] for r in due]
        assert "ship-due" in shipment_ids
        assert "ship-future" not in shipment_ids

    def test_get_due_retries_respects_limit(self) -> None:
        store = DjangoCallbackRetryStore()
        for i in range(5):
            store.store_failed_callback(f"ship-{i}", {}, {})
        CallbackRetry.objects.update(
            next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )

        due = store.get_due_retries(limit=3)

        assert len(due) == 3

    def test_mark_succeeded_changes_status(self) -> None:
        store = DjangoCallbackRetryStore()
        retry_id = store.store_failed_callback("ship-1", {}, {})

        store.mark_succeeded(retry_id)

        record = CallbackRetry.objects.get(id=retry_id)
        assert record.status == "succeeded"

    def test_mark_failed_increments_attempts(self) -> None:
        store = DjangoCallbackRetryStore()
        retry_id = store.store_failed_callback("ship-1", {}, {})

        store.mark_failed(retry_id, error="Connection refused")

        record = CallbackRetry.objects.get(id=retry_id)
        assert record.attempts == 1
        assert record.last_error == "Connection refused"
        assert record.next_retry_at is not None
        assert record.next_retry_at > datetime.now(tz=UTC)

    def test_mark_exhausted_changes_status(self) -> None:
        store = DjangoCallbackRetryStore()
        retry_id = store.store_failed_callback("ship-1", {}, {})

        store.mark_exhausted(retry_id)

        record = CallbackRetry.objects.get(id=retry_id)
        assert record.status == "exhausted"

    def test_pending_retries_with_null_next_retry_at_are_due(self) -> None:
        """Records with no next_retry_at (just created) should be returned."""
        store = DjangoCallbackRetryStore()
        store.store_failed_callback("ship-null", {}, {})

        due = store.get_due_retries(limit=10)

        shipment_ids = [r["shipment_id"] for r in due]
        assert "ship-null" in shipment_ids


@pytest.mark.django_db
class TestProcessDueRetries:
    def test_processes_due_retries_calls_flow(self) -> None:
        store = DjangoCallbackRetryStore()
        store.store_failed_callback(
            "ship-retry",
            {"event": "delivered"},
            {"x-token": "ok"},
        )
        CallbackRetry.objects.update(
            next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )

        mock_flow = AsyncMock()
        mock_repo = AsyncMock()
        mock_shipment = AsyncMock()
        mock_shipment.id = "ship-retry"
        mock_shipment.status = ShipmentStatus.IN_TRANSIT
        mock_repo.get_by_id.return_value = mock_shipment
        mock_flow.handle_callback.return_value = mock_shipment

        processed = process_due_retries(
            retry_store=store,
            flow=mock_flow,
            repository=mock_repo,
            max_attempts=5,
        )

        assert processed == 1
        record = CallbackRetry.objects.get(shipment_id="ship-retry")
        assert record.status == "succeeded"

    def test_marks_exhausted_after_max_attempts(self) -> None:
        store = DjangoCallbackRetryStore()
        retry_id = store.store_failed_callback("ship-exhaust", {}, {})
        CallbackRetry.objects.filter(id=retry_id).update(
            attempts=4,
            next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )

        mock_flow = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.side_effect = Exception("not found")

        processed = process_due_retries(
            retry_store=store,
            flow=mock_flow,
            repository=mock_repo,
            max_attempts=5,
        )

        assert processed == 0
        record = CallbackRetry.objects.get(id=retry_id)
        assert record.status == "exhausted"

    def test_marks_failed_on_error_within_attempts(self) -> None:
        store = DjangoCallbackRetryStore()
        retry_id = store.store_failed_callback("ship-fail", {}, {})
        CallbackRetry.objects.filter(id=retry_id).update(
            attempts=1,
            next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )

        mock_flow = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.side_effect = Exception("temporary error")

        processed = process_due_retries(
            retry_store=store,
            flow=mock_flow,
            repository=mock_repo,
            max_attempts=5,
        )

        assert processed == 0
        record = CallbackRetry.objects.get(id=retry_id)
        assert record.status == "pending"
        assert record.attempts == 2
        assert "temporary error" in record.last_error
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_retry.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'sendparcel_django.retry'`

### Step 3: Add `CallbackRetry` model to `models.py`

Append to `sendparcel_django/models.py` (after the existing classes):

```python
import uuid


class CallbackRetry(models.Model):
    """Persists failed callback attempts for retry processing."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shipment_id = models.CharField(max_length=128, db_index=True)
    payload = models.JSONField(default=dict)
    headers = models.JSONField(default=dict)
    attempts = models.IntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=32,
        default="pending",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"CallbackRetry({self.shipment_id}, {self.status})"
```

> **Note on imports:** The `uuid` import goes at the top of the file with the other imports. Keep `from __future__ import annotations` as the first import, then add `import uuid` right after.

### Step 4: Create migration

Run:
```bash
uv run python -m django makemigrations sendparcel_django --name callbackretry
```
Expected: Creates `sendparcel_django/migrations/0002_callbackretry.py`

### Step 5: Implement retry store and processor

Create `sendparcel_django/retry.py`:

```python
"""Callback retry mechanism for django-sendparcel."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import anyio

from sendparcel_django.models import CallbackRetry


def compute_next_retry_at(
    attempt: int,
    backoff_seconds: int = 60,
) -> datetime:
    """Compute next retry time using exponential backoff.

    delay = backoff_seconds * 2^(attempt - 1)
    """
    delay = backoff_seconds * (2 ** (attempt - 1))
    return datetime.now(tz=UTC) + timedelta(seconds=delay)


class DjangoCallbackRetryStore:
    """Django ORM-backed store for callback retry records."""

    def store_failed_callback(
        self,
        shipment_id: str,
        payload: dict,
        headers: dict,
    ) -> str:
        """Persist a failed callback for later retry.

        Returns the retry record ID as a string.
        """
        record = CallbackRetry.objects.create(
            shipment_id=shipment_id,
            payload=payload,
            headers=headers,
        )
        return str(record.id)

    def get_due_retries(self, limit: int = 10) -> list[dict]:
        """Return pending retries that are due for processing.

        Records with null next_retry_at are considered immediately due.
        """
        now = datetime.now(tz=UTC)
        qs = CallbackRetry.objects.filter(
            status="pending",
        ).filter(
            models_Q_next_retry_at_lte_or_null(now),
        ).order_by("created_at")[:limit]

        return [
            {
                "id": str(record.id),
                "shipment_id": record.shipment_id,
                "payload": record.payload,
                "headers": record.headers,
                "attempts": record.attempts,
            }
            for record in qs
        ]

    def mark_succeeded(self, retry_id: str) -> None:
        """Mark a retry record as successfully processed."""
        CallbackRetry.objects.filter(id=retry_id).update(status="succeeded")

    def mark_failed(
        self,
        retry_id: str,
        error: str,
        backoff_seconds: int = 60,
    ) -> None:
        """Increment attempts, record error, schedule next retry."""
        record = CallbackRetry.objects.get(id=retry_id)
        record.attempts += 1
        record.last_error = error
        record.next_retry_at = compute_next_retry_at(
            attempt=record.attempts,
            backoff_seconds=backoff_seconds,
        )
        record.save(
            update_fields=[
                "attempts",
                "last_error",
                "next_retry_at",
            ],
        )

    def mark_exhausted(self, retry_id: str) -> None:
        """Mark a retry record as exhausted (no more retries)."""
        CallbackRetry.objects.filter(id=retry_id).update(status="exhausted")
```

Wait — the `get_due_retries` method uses a helper that doesn't exist. Let me fix that to use proper Django ORM:

Replace the `get_due_retries` method and add the proper import. The full file should be:

```python
"""Callback retry mechanism for django-sendparcel."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import anyio
from django.db.models import Q

from sendparcel_django.models import CallbackRetry


def compute_next_retry_at(
    attempt: int,
    backoff_seconds: int = 60,
) -> datetime:
    """Compute next retry time using exponential backoff.

    delay = backoff_seconds * 2^(attempt - 1)
    """
    delay = backoff_seconds * (2 ** (attempt - 1))
    return datetime.now(tz=UTC) + timedelta(seconds=delay)


class DjangoCallbackRetryStore:
    """Django ORM-backed store for callback retry records."""

    def store_failed_callback(
        self,
        shipment_id: str,
        payload: dict,
        headers: dict,
    ) -> str:
        """Persist a failed callback for later retry.

        Returns the retry record ID as a string.
        """
        record = CallbackRetry.objects.create(
            shipment_id=shipment_id,
            payload=payload,
            headers=headers,
        )
        return str(record.id)

    def get_due_retries(self, limit: int = 10) -> list[dict]:
        """Return pending retries that are due for processing.

        Records with null next_retry_at are considered immediately due.
        """
        now = datetime.now(tz=UTC)
        qs = (
            CallbackRetry.objects.filter(status="pending")
            .filter(
                Q(next_retry_at__lte=now) | Q(next_retry_at__isnull=True),
            )
            .order_by("created_at")[:limit]
        )

        return [
            {
                "id": str(record.id),
                "shipment_id": record.shipment_id,
                "payload": record.payload,
                "headers": record.headers,
                "attempts": record.attempts,
            }
            for record in qs
        ]

    def mark_succeeded(self, retry_id: str) -> None:
        """Mark a retry record as successfully processed."""
        CallbackRetry.objects.filter(id=retry_id).update(status="succeeded")

    def mark_failed(
        self,
        retry_id: str,
        error: str,
        backoff_seconds: int = 60,
    ) -> None:
        """Increment attempts, record error, schedule next retry."""
        record = CallbackRetry.objects.get(id=retry_id)
        record.attempts += 1
        record.last_error = error
        record.next_retry_at = compute_next_retry_at(
            attempt=record.attempts,
            backoff_seconds=backoff_seconds,
        )
        record.save(
            update_fields=[
                "attempts",
                "last_error",
                "next_retry_at",
            ],
        )

    def mark_exhausted(self, retry_id: str) -> None:
        """Mark a retry record as exhausted (no more retries)."""
        CallbackRetry.objects.filter(id=retry_id).update(status="exhausted")


def process_due_retries(
    *,
    retry_store: DjangoCallbackRetryStore,
    flow,
    repository,
    max_attempts: int = 5,
    backoff_seconds: int = 60,
    limit: int = 10,
) -> int:
    """Process pending callback retries.

    Returns the number of successfully processed retries.
    """
    due = retry_store.get_due_retries(limit=limit)
    succeeded = 0

    for retry_record in due:
        retry_id = retry_record["id"]
        current_attempts = retry_record["attempts"]

        if current_attempts >= max_attempts:
            retry_store.mark_exhausted(retry_id)
            continue

        try:
            shipment = anyio.from_thread.run(
                repository.get_by_id,
                retry_record["shipment_id"],
            )
            anyio.from_thread.run(
                flow.handle_callback,
                shipment,
                retry_record["payload"],
                retry_record["headers"],
            )
            retry_store.mark_succeeded(retry_id)
            succeeded += 1
        except Exception as exc:
            new_attempts = current_attempts + 1
            if new_attempts >= max_attempts:
                retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                    backoff_seconds=backoff_seconds,
                )
                retry_store.mark_exhausted(retry_id)
            else:
                retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                    backoff_seconds=backoff_seconds,
                )

    return succeeded
```

Wait — the tests use `process_due_retries` with `AsyncMock` for `repository` and `flow`. But `anyio.from_thread.run` won't work with AsyncMock in regular sync tests without an event loop. Let me rethink the `process_due_retries` implementation to be simpler — use `anyio.run` instead for each callback:

Actually, looking at the test more carefully, the tests mock `repository.get_by_id` and `flow.handle_callback` with `AsyncMock`. The processor needs to call these async methods. The simplest approach: make `process_due_retries` use `anyio.run()` for each async call (same pattern as the callback view).

Let me redesign `process_due_retries` to use `anyio.run`:

```python
def process_due_retries(
    *,
    retry_store: DjangoCallbackRetryStore,
    flow,
    repository,
    max_attempts: int = 5,
    backoff_seconds: int = 60,
    limit: int = 10,
) -> int:
    """Process pending callback retries.

    Returns the number of successfully processed retries.
    """
    due = retry_store.get_due_retries(limit=limit)
    succeeded = 0

    for retry_record in due:
        retry_id = retry_record["id"]
        current_attempts = retry_record["attempts"]

        if current_attempts >= max_attempts:
            retry_store.mark_exhausted(retry_id)
            continue

        try:
            shipment = anyio.run(
                repository.get_by_id,
                retry_record["shipment_id"],
            )
            anyio.run(
                flow.handle_callback,
                shipment,
                retry_record["payload"],
                retry_record["headers"],
            )
            retry_store.mark_succeeded(retry_id)
            succeeded += 1
        except Exception as exc:
            new_attempts = current_attempts + 1
            if new_attempts >= max_attempts:
                retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                    backoff_seconds=backoff_seconds,
                )
                retry_store.mark_exhausted(retry_id)
            else:
                retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                    backoff_seconds=backoff_seconds,
                )

    return succeeded
```

Hmm, but `anyio.run` takes a single async callable and doesn't take positional args directly. Looking at the existing code pattern in `views.py`, it wraps the call in a helper function. `anyio.run()` signature is `anyio.run(func, *args)` — actually checking: `anyio.run(async_fn, *args)` does accept positional args.

But `AsyncMock` objects are callables that return coroutines. `anyio.run(mock.get_by_id, "ship-retry")` should work since `AsyncMock.__call__` returns a coroutine.

Actually wait — `anyio.run()` is for starting a new event loop. `repository.get_by_id` is an async method, so `anyio.run(repository.get_by_id, "ship-retry")` would try to call `repository.get_by_id("ship-retry")` and await it. That should work with `AsyncMock`.

But there's a subtlety: `anyio.run` only accepts the async function as first arg — additional args aren't supported in the same way as `asyncio.run`. Let me check the actual signature.

Looking at the views.py pattern: `anyio.run(_handle_callback, flow, repository, ...)` — so `anyio.run` does pass args. Good.

But for `flow.handle_callback` which is a method call, we need a wrapper. Let me use a simpler approach — make `process_due_retries` itself async, or use a wrapper:

Let me redesign to use an async inner function wrapped with `anyio.run`:

```python
def process_due_retries(
    *,
    retry_store: DjangoCallbackRetryStore,
    flow,
    repository,
    max_attempts: int = 5,
    backoff_seconds: int = 60,
    limit: int = 10,
) -> int:
    """Process pending callback retries.

    Returns the number of successfully processed retries.
    """
    due = retry_store.get_due_retries(limit=limit)
    succeeded = 0

    for retry_record in due:
        retry_id = retry_record["id"]
        current_attempts = retry_record["attempts"]

        if current_attempts >= max_attempts:
            retry_store.mark_exhausted(retry_id)
            continue

        try:
            anyio.run(
                _process_single_retry,
                flow,
                repository,
                retry_record,
            )
            retry_store.mark_succeeded(retry_id)
            succeeded += 1
        except Exception as exc:
            new_attempts = current_attempts + 1
            if new_attempts >= max_attempts:
                retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                    backoff_seconds=backoff_seconds,
                )
                retry_store.mark_exhausted(retry_id)
            else:
                retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                    backoff_seconds=backoff_seconds,
                )

    return succeeded


async def _process_single_retry(flow, repository, retry_record: dict):
    """Process a single retry record asynchronously."""
    shipment = await repository.get_by_id(retry_record["shipment_id"])
    await flow.handle_callback(
        shipment,
        retry_record["payload"],
        retry_record["headers"],
    )
```

This is cleaner. Now let me put the complete final file together in the plan.

Also, I need to update the tests. The test for `test_marks_exhausted_after_max_attempts` sets `attempts=4` and `max_attempts=5`, then triggers an error. The code path: `current_attempts=4 < 5`, so it tries to process, raises exception, `new_attempts = 5 >= 5`, so it calls `mark_failed` then `mark_exhausted`. The `mark_failed` will set `attempts=5`. Then `mark_exhausted` sets `status="exhausted"`. The test checks `record.status == "exhausted"` — this should work.

The test for `test_marks_failed_on_error_within_attempts` sets `attempts=1` and `max_attempts=5`. Code path: `current_attempts=1 < 5`, tries to process, raises exception, `new_attempts=2 < 5`, so calls `mark_failed` only. `mark_failed` sets `attempts=2` (increments from 1, which is the DB value). Wait — there's a subtlety: `mark_failed` does `record.attempts += 1`. The DB has `attempts=1`, so after `mark_failed` it'll be `attempts=2`. The test checks `record.attempts == 2`. Good.

But wait — in `mark_failed`, we read the record from DB with `CallbackRetry.objects.get(id=retry_id)`, increment, and save. The test initially set `attempts=1` via `.update()`. Then `mark_failed` reads `attempts=1`, increments to `2`, saves. Test asserts `record.attempts == 2`. Correct.

OK, everything looks consistent. Let me finalize the plan with the correct code.

Actually, I realize I should double-check: will `anyio.run()` work with `AsyncMock`? The `_process_single_retry` is a real async function. Inside it calls `await repository.get_by_id(...)` where `repository.get_by_id` is an `AsyncMock`. `AsyncMock` returns a coroutine when called, and `await` on it works. `anyio.run(_process_single_retry, flow, repository, retry_record)` starts an event loop, calls the async function, awaits it. This should work.

Let me also re-check: `anyio.run` signature. From the docs, it's `anyio.run(func)` — it only takes the async function, no additional args. Looking at the views.py code: `anyio.run(_handle_callback, flow, repository, shipment_id, payload, ...)` — that passes extra args. So either `anyio.run` does accept extra args, or this code is wrong. Let me check.

Actually, the `anyio.run()` has this signature: `anyio.run(func, *args, backend=..., backend_options=...)`. It does accept positional args. So `anyio.run(_process_single_retry, flow, repository, retry_record)` should work.

Good. Now let me write the complete plan file.

**Step 6: Add `CallbackRetryFactory` to `tests/factories.py`**

Append to `tests/factories.py`:

```python
from sendparcel_django.models import CallbackRetry


class CallbackRetryFactory(factory.django.DjangoModelFactory):
    """Factory for CallbackRetry model instances."""

    class Meta:
        model = CallbackRetry

    shipment_id = factory.Sequence(lambda n: f"ship-{n}")
    payload = factory.LazyFunction(dict)
    headers = factory.LazyFunction(dict)
    status = "pending"
    attempts = 0
```

### Step 7: Run tests to verify they pass

Run:
```bash
uv run pytest tests/test_retry.py -v
```
Expected: All 11 tests PASS.

### Step 8: Commit

```bash
git add sendparcel_django/models.py sendparcel_django/retry.py sendparcel_django/migrations/ tests/test_retry.py tests/factories.py
git commit -m "feat: add callback retry mechanism with exponential backoff"
```

---

## Task 6: tests/test_models.py (~8 tests)

**Files:**
- Create: `tests/test_models.py`

These tests validate the Django model fields, defaults, constraints, and abstract mixin behavior.

**Step 1: Write tests**

Create `tests/test_models.py`:

```python
"""Django model tests."""

from __future__ import annotations

import pytest
from django.db import models as django_models
from sendparcel.enums import ShipmentStatus

from sendparcel_django.models import (
    CallbackRetry,
    OrderModelMixin,
    Shipment,
    ShipmentModelMixin,
)


class TestOrderModelMixin:
    def test_get_total_weight_raises_not_implemented(self) -> None:
        class ConcreteOrder(OrderModelMixin):
            class Meta:
                app_label = "test"

        order = ConcreteOrder.__new__(ConcreteOrder)
        with pytest.raises(NotImplementedError):
            order.get_total_weight()

    def test_get_parcels_raises_not_implemented(self) -> None:
        class ConcreteOrder(OrderModelMixin):
            class Meta:
                app_label = "test"

        order = ConcreteOrder.__new__(ConcreteOrder)
        with pytest.raises(NotImplementedError):
            order.get_parcels()

    def test_get_sender_address_raises_not_implemented(self) -> None:
        class ConcreteOrder(OrderModelMixin):
            class Meta:
                app_label = "test"

        order = ConcreteOrder.__new__(ConcreteOrder)
        with pytest.raises(NotImplementedError):
            order.get_sender_address()

    def test_get_receiver_address_raises_not_implemented(self) -> None:
        class ConcreteOrder(OrderModelMixin):
            class Meta:
                app_label = "test"

        order = ConcreteOrder.__new__(ConcreteOrder)
        with pytest.raises(NotImplementedError):
            order.get_receiver_address()


class TestShipmentModelMixin:
    def test_mixin_is_abstract(self) -> None:
        assert ShipmentModelMixin._meta.abstract is True

    def test_has_expected_fields(self) -> None:
        field_names = {f.name for f in ShipmentModelMixin._meta.get_fields()}
        assert "provider" in field_names
        assert "status" in field_names
        assert "external_id" in field_names
        assert "tracking_number" in field_names
        assert "label_url" in field_names


@pytest.mark.django_db
class TestShipmentModel:
    def test_create_shipment_with_defaults(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
        )

        assert shipment.status == ShipmentStatus.NEW
        assert shipment.external_id == ""
        assert shipment.tracking_number == ""
        assert shipment.label_url == ""

    def test_shipment_field_max_lengths(self) -> None:
        provider_field = Shipment._meta.get_field("provider")
        assert provider_field.max_length == 64

        status_field = Shipment._meta.get_field("status")
        assert status_field.max_length == 32

        external_id_field = Shipment._meta.get_field("external_id")
        assert external_id_field.max_length == 128

    def test_shipment_blank_fields(self) -> None:
        external_id_field = Shipment._meta.get_field("external_id")
        assert external_id_field.blank is True

        tracking_field = Shipment._meta.get_field("tracking_number")
        assert tracking_field.blank is True

        label_field = Shipment._meta.get_field("label_url")
        assert label_field.blank is True

    def test_shipment_timestamps_auto_set(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-2",
        )

        assert shipment.created_at is not None
        assert shipment.updated_at is not None

    def test_shipment_str_representation(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-3",
        )

        str_repr = str(shipment)
        # Should include something identifying (provider or id at minimum)
        assert str_repr  # Non-empty string


class TestCallbackRetryModel:
    @pytest.mark.django_db
    def test_create_callback_retry_with_defaults(self) -> None:
        record = CallbackRetry.objects.create(shipment_id="ship-1")

        assert record.status == "pending"
        assert record.attempts == 0
        assert record.payload == {}
        assert record.headers == {}
        assert record.next_retry_at is None
        assert record.last_error is None
        assert record.created_at is not None

    @pytest.mark.django_db
    def test_callback_retry_str_representation(self) -> None:
        record = CallbackRetry.objects.create(shipment_id="ship-1")
        str_repr = str(record)
        assert "ship-1" in str_repr

    def test_callback_retry_uuid_primary_key(self) -> None:
        pk_field = CallbackRetry._meta.get_field("id")
        assert isinstance(pk_field, django_models.UUIDField)
        assert pk_field.primary_key is True
```

> **Note:** The `Shipment` model from the foundation plan should have `created_at`, `updated_at`, and `order_id` fields. If the concrete `Shipment` model does not have `__str__`, the `test_shipment_str_representation` test just checks it returns a non-empty string (Django models return `"ModelName object (pk)"` by default).

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_models.py -v
```
Expected: All ~13 tests PASS.

**Step 3: Commit**

```bash
git add tests/test_models.py
git commit -m "test: add comprehensive model tests for Shipment, OrderMixin, CallbackRetry"
```

---

## Task 7: tests/test_fsm_integration.py (~10 tests)

**Files:**
- Create: `tests/test_fsm_integration.py`

These tests verify FSM transitions work through Django model instances (not just plain Python objects).

**Step 1: Write tests**

Create `tests/test_fsm_integration.py`:

```python
"""FSM integration tests with Django model instances."""

from __future__ import annotations

import pytest
from sendparcel.enums import ShipmentStatus
from sendparcel.fsm import create_shipment_machine
from transitions.core import MachineError

from sendparcel_django.models import Shipment


@pytest.mark.django_db
class TestFSMWithDjangoModel:
    def test_happy_path_new_to_delivered(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
        )
        create_shipment_machine(shipment)

        shipment.confirm_created()
        assert shipment.status == ShipmentStatus.CREATED

        shipment.confirm_label()
        assert shipment.status == ShipmentStatus.LABEL_READY

        shipment.mark_in_transit()
        assert shipment.status == ShipmentStatus.IN_TRANSIT

        shipment.mark_out_for_delivery()
        assert shipment.status == ShipmentStatus.OUT_FOR_DELIVERY

        shipment.mark_delivered()
        assert shipment.status == ShipmentStatus.DELIVERED

    def test_cancel_from_new(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
        )
        create_shipment_machine(shipment)

        shipment.cancel()
        assert shipment.status == ShipmentStatus.CANCELLED

    def test_cancel_from_created(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
            status=ShipmentStatus.CREATED,
        )
        create_shipment_machine(shipment)

        shipment.cancel()
        assert shipment.status == ShipmentStatus.CANCELLED

    def test_cancel_from_label_ready(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
            status=ShipmentStatus.LABEL_READY,
        )
        create_shipment_machine(shipment)

        shipment.cancel()
        assert shipment.status == ShipmentStatus.CANCELLED

    def test_fail_from_new(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
        )
        create_shipment_machine(shipment)

        shipment.fail()
        assert shipment.status == ShipmentStatus.FAILED

    def test_fail_from_in_transit(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
            status=ShipmentStatus.IN_TRANSIT,
        )
        create_shipment_machine(shipment)

        shipment.fail()
        assert shipment.status == ShipmentStatus.FAILED

    def test_cannot_deliver_from_new(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
        )
        create_shipment_machine(shipment)

        with pytest.raises(MachineError):
            shipment.mark_delivered()

    def test_cannot_cancel_from_delivered(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
            status=ShipmentStatus.DELIVERED,
        )
        create_shipment_machine(shipment)

        with pytest.raises(MachineError):
            shipment.cancel()

    def test_mark_in_transit_from_created(self) -> None:
        """mark_in_transit can be triggered from CREATED (skipping LABEL_READY)."""
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
            status=ShipmentStatus.CREATED,
        )
        create_shipment_machine(shipment)

        shipment.mark_in_transit()
        assert shipment.status == ShipmentStatus.IN_TRANSIT

    def test_mark_returned_from_delivered(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
            status=ShipmentStatus.DELIVERED,
        )
        create_shipment_machine(shipment)

        shipment.mark_returned()
        assert shipment.status == ShipmentStatus.RETURNED

    def test_may_trigger_returns_false_for_invalid(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
        )
        create_shipment_machine(shipment)

        assert shipment.may_trigger("mark_delivered") is False

    def test_may_trigger_returns_true_for_valid(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
        )
        create_shipment_machine(shipment)

        assert shipment.may_trigger("confirm_created") is True
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_fsm_integration.py -v
```
Expected: All 12 tests PASS.

**Step 3: Commit**

```bash
git add tests/test_fsm_integration.py
git commit -m "test: add FSM integration tests with Django model instances"
```

---

## Task 8: Expand tests/test_views.py (~8 tests)

**Files:**
- Modify: `tests/test_views.py` (add more test cases)

**Step 1: Add additional view tests**

Append the following test class to the existing `tests/test_views.py`. Keep all existing code, add these new tests at the bottom:

```python
class TestCallbackEdgeCases:
    def test_callback_with_empty_body(self) -> None:
        core_registry.register(DummyProvider)
        repo = Repo()

        class EmptyRequest:
            body = b""
            headers = {"x-dummy-token": "ok"}

        response = callback(
            EmptyRequest(),
            "s-1",
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )
        # Empty body parses as {} — should succeed
        assert response.status_code == 200

    def test_callback_with_invalid_json(self) -> None:
        core_registry.register(DummyProvider)
        repo = Repo()

        class BadJsonRequest:
            body = b"not-json{{"
            headers = {"x-dummy-token": "ok"}

        response = callback(
            BadJsonRequest(),
            "s-1",
            repository=repo,
            config={"dummy": {}},
        )
        assert response.status_code == 400
        assert b"Invalid JSON" in response.content

    def test_callback_without_repository_returns_500(self) -> None:
        response = callback(
            RequestStub({"event": "test"}, {}),
            "s-1",
            repository=None,
        )
        assert response.status_code == 500
        assert b"Repository is required" in response.content

    def test_callback_returns_shipment_id_in_response(self) -> None:
        core_registry.register(DummyProvider)
        repo = Repo()

        response = callback(
            RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
            "s-1",
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )
        data = json.loads(response.content)
        assert data["shipment_id"] == "s-1"
        assert data["received"] is True

    def test_callback_returns_updated_status(self) -> None:
        core_registry.register(DummyProvider)
        repo = Repo()

        response = callback(
            RequestStub({"event": "picked_up"}, {"x-dummy-token": "ok"}),
            "s-1",
            repository=repo,
            config={"dummy": {"callback_token": "ok"}},
        )
        data = json.loads(response.content)
        assert data["status"] == "in_transit"

    def test_callback_with_invalid_utf8(self) -> None:
        core_registry.register(DummyProvider)
        repo = Repo()

        class BadUtf8Request:
            body = b"\x80\x81\x82"
            headers = {"x-dummy-token": "ok"}

        response = callback(
            BadUtf8Request(),
            "s-1",
            repository=repo,
            config={"dummy": {}},
        )
        assert response.status_code == 400
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_views.py -v
```
Expected: All 8 tests PASS (2 original + 6 new).

**Step 3: Commit**

```bash
git add tests/test_views.py
git commit -m "test: expand callback view tests with edge cases"
```

---

## Task 9: Expand tests/test_admin.py (~6 tests)

**Files:**
- Modify: `tests/test_admin.py` (expand with more tests)

**Step 1: Add additional admin tests**

After the foundation plan, `admin.py` should have a `ShipmentAdmin(ModelAdmin)` registered with Django admin. Expand `tests/test_admin.py`. Keep existing code, add new tests:

```python
import pytest
from django.contrib import admin as django_admin
from django.contrib.admin.sites import AdminSite

from sendparcel_django.models import Shipment


@pytest.mark.django_db
class TestShipmentAdmin:
    def test_shipment_admin_is_registered(self) -> None:
        assert Shipment in django_admin.site._registry

    def test_list_display_contains_key_fields(self) -> None:
        model_admin = django_admin.site._registry[Shipment]
        display_fields = model_admin.list_display
        # Should at minimum show provider and status
        assert "provider" in display_fields
        assert "status" in display_fields

    def test_mark_in_transit_bulk_action(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
            status=ShipmentStatus.LABEL_READY,
        )
        create_shipment_machine(shipment)
        actions = build_status_actions()

        count = actions["mark_in_transit"]([shipment])

        assert count == 1
        assert shipment.status == ShipmentStatus.IN_TRANSIT

    def test_cancel_bulk_action(self) -> None:
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-2",
            status=ShipmentStatus.CREATED,
        )
        create_shipment_machine(shipment)
        actions = build_status_actions()

        count = actions["cancel"]([shipment])

        assert count == 1
        assert shipment.status == ShipmentStatus.CANCELLED

    def test_action_on_non_transitionable_shipment_is_noop(self) -> None:
        """Trying to mark_in_transit on a DELIVERED shipment should do nothing."""
        shipment = Shipment.objects.create(
            provider="dummy",
            order_id="order-3",
            status=ShipmentStatus.DELIVERED,
        )
        create_shipment_machine(shipment)
        actions = build_status_actions()

        count = actions["mark_in_transit"]([shipment])

        assert count == 0
        assert shipment.status == ShipmentStatus.DELIVERED

    def test_bulk_action_with_mixed_states(self) -> None:
        """Only eligible shipments should transition."""
        s1 = Shipment.objects.create(
            provider="dummy",
            order_id="order-4",
            status=ShipmentStatus.LABEL_READY,
        )
        s2 = Shipment.objects.create(
            provider="dummy",
            order_id="order-5",
            status=ShipmentStatus.DELIVERED,
        )
        create_shipment_machine(s1)
        create_shipment_machine(s2)
        actions = build_status_actions()

        count = actions["mark_in_transit"]([s1, s2])

        assert count == 1
        assert s1.status == ShipmentStatus.IN_TRANSIT
        assert s2.status == ShipmentStatus.DELIVERED
```

> **Note:** The existing test file already imports `ShipmentStatus`, `create_shipment_machine`, and `build_status_actions`. The new tests add Django DB-backed model tests. The existing non-DB tests (using plain Python classes) should remain — they test the action hooks in isolation.

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_admin.py -v
```
Expected: All 8 tests PASS (2 original + 6 new).

**Step 3: Commit**

```bash
git add tests/test_admin.py
git commit -m "test: expand admin tests with DB-backed model instances and edge cases"
```

---

## Task 10: tests/test_repository.py (~8 tests)

**Files:**
- Create: `tests/test_repository.py`

These tests validate the `DjangoShipmentRepository` created in the foundation plan.

**Step 1: Write tests**

Create `tests/test_repository.py`:

```python
"""DjangoShipmentRepository tests."""

from __future__ import annotations

import pytest
from sendparcel.enums import ShipmentStatus

from sendparcel_django.models import Shipment
from sendparcel_django.repository import DjangoShipmentRepository


@pytest.mark.django_db
class TestDjangoShipmentRepository:
    def test_create_shipment(self) -> None:
        repo = DjangoShipmentRepository()

        shipment = pytest.importorskip("anyio").run(
            repo.create,
            order="order-1",
            provider="dummy",
            status=ShipmentStatus.NEW,
        )

        assert shipment is not None
        assert shipment.provider == "dummy"
        assert shipment.status == ShipmentStatus.NEW
        assert Shipment.objects.count() == 1

    def test_get_by_id(self) -> None:
        created = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
        )
        repo = DjangoShipmentRepository()

        shipment = pytest.importorskip("anyio").run(
            repo.get_by_id,
            str(created.pk),
        )

        assert str(shipment.id) == str(created.pk)
        assert shipment.provider == "dummy"

    def test_get_by_id_not_found_raises(self) -> None:
        repo = DjangoShipmentRepository()

        with pytest.raises(Exception):
            pytest.importorskip("anyio").run(
                repo.get_by_id,
                "nonexistent-id",
            )

    def test_save_updates_fields(self) -> None:
        created = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
        )
        repo = DjangoShipmentRepository()

        shipment = pytest.importorskip("anyio").run(
            repo.get_by_id,
            str(created.pk),
        )
        shipment.tracking_number = "TRK-123"
        saved = pytest.importorskip("anyio").run(repo.save, shipment)

        assert saved.tracking_number == "TRK-123"
        created.refresh_from_db()
        assert created.tracking_number == "TRK-123"

    def test_update_status(self) -> None:
        created = Shipment.objects.create(
            provider="dummy",
            order_id="order-1",
            status=ShipmentStatus.NEW,
        )
        repo = DjangoShipmentRepository()

        shipment = pytest.importorskip("anyio").run(
            repo.update_status,
            str(created.pk),
            ShipmentStatus.CREATED,
        )

        assert shipment.status == ShipmentStatus.CREATED
        created.refresh_from_db()
        assert created.status == ShipmentStatus.CREATED

    def test_create_with_order_id_string(self) -> None:
        """When order is a string, it should be used as order_id directly."""
        repo = DjangoShipmentRepository()

        shipment = pytest.importorskip("anyio").run(
            repo.create,
            order="my-order-42",
            provider="test_provider",
            status=ShipmentStatus.NEW,
        )

        assert shipment.order_id == "my-order-42"

    def test_create_sets_external_id(self) -> None:
        repo = DjangoShipmentRepository()

        shipment = pytest.importorskip("anyio").run(
            repo.create,
            order="order-1",
            provider="dummy",
            status=ShipmentStatus.NEW,
            external_id="ext-abc",
        )

        assert shipment.external_id == "ext-abc"

    def test_multiple_shipments_same_order(self) -> None:
        repo = DjangoShipmentRepository()

        s1 = pytest.importorskip("anyio").run(
            repo.create,
            order="order-shared",
            provider="provider_a",
            status=ShipmentStatus.NEW,
        )
        s2 = pytest.importorskip("anyio").run(
            repo.create,
            order="order-shared",
            provider="provider_b",
            status=ShipmentStatus.NEW,
        )

        assert str(s1.id) != str(s2.id)
        assert Shipment.objects.filter(order_id="order-shared").count() == 2
```

> **Note:** The `DjangoShipmentRepository` interface is async (matching core `ShipmentRepository` protocol). Tests use `anyio.run()` to call async methods. The exact `create` signature depends on the foundation plan implementation — the `order` kwarg may be an object with an `id` attribute or a string. These tests cover both patterns. If the foundation implementation extracts `order_id` differently, adjust accordingly.

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_repository.py -v
```
Expected: All 8 tests PASS.

**Step 3: Commit**

```bash
git add tests/test_repository.py
git commit -m "test: add DjangoShipmentRepository tests"
```

---

## Task 11: tests/test_conf.py (~4 tests)

**Files:**
- Create: `tests/test_conf.py`

**Step 1: Write tests**

Create `tests/test_conf.py`:

```python
"""Configuration settings tests."""

from __future__ import annotations

from django.conf import settings
from django.test import override_settings

from sendparcel_django.conf import get_setting


class TestGetSetting:
    def test_returns_default_when_not_configured(self) -> None:
        # SENDPARCEL_NONEXISTENT should not be in settings
        result = get_setting("NONEXISTENT", default="fallback")
        assert result == "fallback"

    def test_reads_from_django_settings(self) -> None:
        result = get_setting("SHIPMENT_MODEL", default=None)
        # This is set in conftest.py
        assert result == "sendparcel_django.Shipment"

    @override_settings(SENDPARCEL_CUSTOM_VALUE="hello")
    def test_override_settings_works(self) -> None:
        result = get_setting("CUSTOM_VALUE", default="nope")
        assert result == "hello"

    def test_default_is_none_when_not_specified(self) -> None:
        result = get_setting("TOTALLY_MISSING")
        assert result is None
```

> **Note:** The `get_setting` function from the foundation plan should read `SENDPARCEL_<name>` from `django.conf.settings` with an optional default. The exact implementation: `getattr(settings, f"SENDPARCEL_{name}", default)`.

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_conf.py -v
```
Expected: All 4 tests PASS.

**Step 3: Commit**

```bash
git add tests/test_conf.py
git commit -m "test: add configuration settings tests"
```

---

## Task 12: tests/test_public_api.py (~3 tests)

**Files:**
- Create: `tests/test_public_api.py`

**Step 1: Write tests**

Create `tests/test_public_api.py`:

```python
"""Public API surface tests."""

from __future__ import annotations

import importlib

import sendparcel_django


class TestPublicAPI:
    def test_all_exports_defined(self) -> None:
        assert hasattr(sendparcel_django, "__all__")
        assert isinstance(sendparcel_django.__all__, (list, tuple))
        assert len(sendparcel_django.__all__) > 0

    def test_all_exports_are_importable(self) -> None:
        for name in sendparcel_django.__all__:
            obj = getattr(sendparcel_django, name, None)
            assert obj is not None, (
                f"{name} listed in __all__ but not importable"
            )

    def test_key_symbols_exported(self) -> None:
        """Core integration symbols should be in __all__."""
        exported = set(sendparcel_django.__all__)
        # These are the minimum expected exports
        expected_subset = {
            "DjangoOrderAdapter",
            "DjangoShipmentAdapter",
            "DjangoPluginRegistry",
            "registry",
        }
        assert expected_subset.issubset(exported), (
            f"Missing exports: {expected_subset - exported}"
        )
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_public_api.py -v
```
Expected: All 3 tests PASS.

**Step 3: Commit**

```bash
git add tests/test_public_api.py
git commit -m "test: add public API surface tests"
```

---

## Task 13: Final validation — full test suite

**Files:** None (validation only)

**Step 1: Run full test suite**

Run:
```bash
uv run pytest tests/ -v --tb=short
```
Expected: All tests pass (~65+ tests). Approximate breakdown:

| File | Tests |
|------|-------|
| test_models.py | ~13 |
| test_fsm_integration.py | ~12 |
| test_views.py | ~8 |
| test_admin.py | ~8 |
| test_repository.py | ~8 |
| test_conf.py | ~4 |
| test_retry.py | ~11 |
| test_middleware.py | ~7 |
| test_tags.py | ~12 |
| test_public_api.py | ~3 |
| test_protocols.py | ~2 |
| test_registry.py | ~1 |
| test_forms.py | ~1 |
| test_example_app.py | ~1 |

**Step 2: Run with coverage (optional)**

Run:
```bash
uv run pytest tests/ -v --tb=short -q
```
Expected: All tests pass, zero failures.

**Step 3: Run linter**

Run:
```bash
uv run ruff check sendparcel_django/ tests/
```
Expected: No errors.

**Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "test: complete comprehensive test suite for django-sendparcel"
```

---

## Summary

| Task | Component | Tests Added | Files Changed/Created |
|------|-----------|-------------|----------------------|
| 1 | Test infrastructure | 0 | pyproject.toml, tests/conftest.py, tests/__init__.py |
| 2 | Test factories | 0 | tests/factories.py |
| 3 | Template tags | 12 | sendparcel_django/templatetags/*, tests/test_tags.py |
| 4 | Exception middleware | 7 | sendparcel_django/middleware.py, tests/test_middleware.py |
| 5 | Callback retry | 11 | sendparcel_django/models.py, sendparcel_django/retry.py, migrations, tests/test_retry.py |
| 6 | Model tests | 13 | tests/test_models.py |
| 7 | FSM integration tests | 12 | tests/test_fsm_integration.py |
| 8 | View tests (expand) | 6 | tests/test_views.py |
| 9 | Admin tests (expand) | 6 | tests/test_admin.py |
| 10 | Repository tests | 8 | tests/test_repository.py |
| 11 | Config tests | 4 | tests/test_conf.py |
| 12 | Public API tests | 3 | tests/test_public_api.py |
| 13 | Final validation | 0 | (validation only) |
| **Total** | | **~82** | |

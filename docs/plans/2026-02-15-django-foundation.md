# Django Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the missing Django foundation to django-sendparcel: AppConfig, settings integration, swappable models, migrations, model exports, proper exception handling in views, a Django ORM repository, complete admin, and registry cleanup.

**Architecture:** The package follows Django conventions with a flat layout at `sendparcel_django/`. We add a proper `AppConfig` (apps.py) that triggers plugin discovery on `ready()`, a settings reader module (conf.py), swappable concrete models via the `swapper` library, a `DjangoShipmentRepository` wrapping Django ORM with `sync_to_async`, and a full `ShipmentAdmin` with all FSM transition actions. The callback view gets proper exception-to-HTTP-status mapping. Tests use `pytest-django` with an in-memory SQLite database.

**Tech Stack:** Django 6.x, swapper, asgiref (sync_to_async), pytest-django, python-sendparcel core (fsm, exceptions, flow, registry)

---

### Task 1: Add pytest-django and swapper dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add swapper to project dependencies and pytest-django to dev dependencies**

In `pyproject.toml`, update the `dependencies` list and `dev` optional-dependencies:

```toml
dependencies = [
    "Django>=5.2",
    "python-sendparcel>=0.1.0",
    "anyio>=4.0",
    "swapper>=1.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "pytest-django>=4.9.0",
    "ruff>=0.9.0",
]
```

**Step 2: Install the new dependencies**

Run (from `django-sendparcel/`):
```bash
uv sync --all-extras
```
Expected: Dependencies install successfully, including `swapper` and `pytest-django`.

**Step 3: Verify imports work**

Run (from `django-sendparcel/`):
```bash
uv run python -c "import swapper; print('swapper OK'); import pytest_django; print('pytest-django OK')"
```
Expected:
```
swapper OK
pytest-django OK
```

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add swapper and pytest-django dependencies"
```

---

### Task 2: Upgrade test infrastructure to pytest-django

**Files:**
- Modify: `tests/conftest.py`
- Modify: `pyproject.toml` (pytest config section)

This task replaces the manual `settings.configure()` in conftest.py with a proper `DJANGO_SETTINGS_MODULE` approach that `pytest-django` expects, and configures Django with `INSTALLED_APPS`, `DATABASES`, etc. so that models and migrations work in tests.

**Step 1: Update pyproject.toml pytest config**

Add `DJANGO_SETTINGS_MODULE` to `[tool.pytest.ini_options]` in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
DJANGO_SETTINGS_MODULE = "tests.settings"
```

**Step 2: Create tests/settings.py with full Django test settings**

Create file `tests/settings.py`:

```python
"""Django settings for django-sendparcel test suite."""

SECRET_KEY = "test-secret-key-not-for-production"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "sendparcel_django",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = True

ROOT_URLCONF = "tests.urls"

SENDPARCEL_SHIPMENT_MODEL = "sendparcel_django.Shipment"
```

**Step 3: Create tests/urls.py for URL resolution in tests**

Create file `tests/urls.py`:

```python
"""URL configuration for django-sendparcel test suite."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sendparcel/", include("sendparcel_django.urls")),
]
```

**Step 4: Update tests/conftest.py to remove manual settings.configure()**

Replace the entire contents of `tests/conftest.py`:

```python
"""Shared fixtures for django-sendparcel tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sendparcel.registry import registry as core_registry
from sendparcel_django.registry import registry as django_registry


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

**Step 5: Run existing tests to verify nothing is broken**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/ -v
```
Expected: All 9 existing tests pass. The `pytest-django` plugin is now active (visible in the pytest header output).

**Step 6: Commit**

```bash
git add pyproject.toml tests/settings.py tests/urls.py tests/conftest.py
git commit -m "test: upgrade test infrastructure to pytest-django with proper settings"
```

---

### Task 3: Add AppConfig (apps.py)

**Files:**
- Create: `sendparcel_django/apps.py`
- Modify: `sendparcel_django/__init__.py`
- Test: `tests/test_apps.py`

**Step 1: Write the failing tests for AppConfig**

Create file `tests/test_apps.py`:

```python
"""AppConfig tests."""

from unittest.mock import patch

from django.apps import apps


def test_appconfig_exists_and_has_correct_name():
    config = apps.get_app_config("sendparcel_django")
    assert config.name == "sendparcel_django"


def test_appconfig_has_correct_verbose_name():
    config = apps.get_app_config("sendparcel_django")
    assert config.verbose_name == "SendParcel"


def test_appconfig_has_correct_default_auto_field():
    config = apps.get_app_config("sendparcel_django")
    assert config.default_auto_field == "django.db.models.BigAutoField"


def test_appconfig_ready_calls_registry_discover():
    config = apps.get_app_config("sendparcel_django")
    with patch("sendparcel_django.registry.registry.discover") as mock_discover:
        config.ready()
        mock_discover.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_apps.py -v
```
Expected: FAIL — `django.apps.apps.get_app_config("sendparcel_django")` raises `LookupError` because there is no `AppConfig` yet (though the app is in `INSTALLED_APPS`, Django auto-creates a minimal config without our custom attributes).

**Step 3: Create sendparcel_django/apps.py**

Create file `sendparcel_django/apps.py`:

```python
"""Django AppConfig for sendparcel."""

from django.apps import AppConfig


class SendparcelConfig(AppConfig):
    name = "sendparcel_django"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "SendParcel"

    def ready(self):
        from sendparcel_django.registry import registry

        registry.discover()
```

**Step 4: Update sendparcel_django/__init__.py to set default_app_config**

Add the `default_app_config` line at the top of `sendparcel_django/__init__.py` (after the docstring, before imports):

```python
"""Django adapter for sendparcel."""

default_app_config = "sendparcel_django.apps.SendparcelConfig"

from sendparcel_django.forms import ProviderChoiceForm
from sendparcel_django.protocols import (
    DjangoOrderAdapter,
    DjangoShipmentAdapter,
)
from sendparcel_django.registry import DjangoPluginRegistry, registry

__all__ = [
    "DjangoOrderAdapter",
    "DjangoPluginRegistry",
    "DjangoShipmentAdapter",
    "ProviderChoiceForm",
    "registry",
]
```

**Step 5: Run AppConfig tests to verify they pass**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_apps.py -v
```
Expected: All 4 tests PASS.

**Step 6: Run full test suite to verify no regressions**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/ -v
```
Expected: All tests pass (9 existing + 4 new = 13 total).

**Step 7: Commit**

```bash
git add sendparcel_django/apps.py sendparcel_django/__init__.py tests/test_apps.py
git commit -m "feat: add Django AppConfig with plugin discovery in ready()"
```

---

### Task 4: Add Django settings integration (conf.py)

**Files:**
- Create: `sendparcel_django/conf.py`
- Test: `tests/test_conf.py`

**Step 1: Write the failing tests for conf.py**

Create file `tests/test_conf.py`:

```python
"""Settings integration tests."""

from django.test import override_settings

from sendparcel_django.conf import get_settings


def test_defaults_when_no_settings_defined():
    """All settings return defaults when not set in Django settings."""
    conf = get_settings()
    assert conf.PROVIDER_SETTINGS == {}
    assert conf.DEFAULT_PROVIDER == ""
    assert conf.SHIPMENT_MODEL == "sendparcel_django.Shipment"


@override_settings(
    SENDPARCEL_PROVIDER_SETTINGS={"dummy": {"api_key": "abc123"}},
    SENDPARCEL_DEFAULT_PROVIDER="dummy",
    SENDPARCEL_SHIPMENT_MODEL="myapp.CustomShipment",
)
def test_settings_override_from_django_settings():
    """Settings are read from Django settings when defined."""
    conf = get_settings()
    assert conf.PROVIDER_SETTINGS == {"dummy": {"api_key": "abc123"}}
    assert conf.DEFAULT_PROVIDER == "dummy"
    assert conf.SHIPMENT_MODEL == "myapp.CustomShipment"


def test_get_settings_returns_fresh_values_each_call():
    """get_settings() reads current Django settings (not cached stale values)."""
    conf1 = get_settings()
    assert conf1.DEFAULT_PROVIDER == ""

    with override_settings(SENDPARCEL_DEFAULT_PROVIDER="inpost"):
        conf2 = get_settings()
        assert conf2.DEFAULT_PROVIDER == "inpost"

    conf3 = get_settings()
    assert conf3.DEFAULT_PROVIDER == ""
```

**Step 2: Run tests to verify they fail**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_conf.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'sendparcel_django.conf'`

**Step 3: Create sendparcel_django/conf.py**

Create file `sendparcel_django/conf.py`:

```python
"""Django settings integration for sendparcel."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class SendparcelSettings:
    """Resolved sendparcel configuration from Django settings."""

    PROVIDER_SETTINGS: dict
    DEFAULT_PROVIDER: str
    SHIPMENT_MODEL: str


def get_settings() -> SendparcelSettings:
    """Read sendparcel configuration from Django settings.

    Reads fresh values from ``django.conf.settings`` on every call
    so that ``@override_settings`` in tests works correctly.
    """
    return SendparcelSettings(
        PROVIDER_SETTINGS=getattr(
            settings, "SENDPARCEL_PROVIDER_SETTINGS", {}
        ),
        DEFAULT_PROVIDER=getattr(
            settings, "SENDPARCEL_DEFAULT_PROVIDER", ""
        ),
        SHIPMENT_MODEL=getattr(
            settings,
            "SENDPARCEL_SHIPMENT_MODEL",
            "sendparcel_django.Shipment",
        ),
    )
```

**Step 4: Run tests to verify they pass**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_conf.py -v
```
Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add sendparcel_django/conf.py tests/test_conf.py
git commit -m "feat: add Django settings integration (conf.py)"
```

---

### Task 5: Add swappable models with timestamps

**Files:**
- Modify: `sendparcel_django/models.py`
- Test: `tests/test_models.py`

**Step 1: Write failing tests for model fields and swapper integration**

Create file `tests/test_models.py`:

```python
"""Model tests."""

import pytest
from django.db import models as django_models

from sendparcel_django.models import OrderModelMixin, Shipment, ShipmentModelMixin


class TestOrderModelMixin:
    def test_is_abstract(self):
        assert OrderModelMixin._meta.abstract is True

    def test_get_total_weight_raises_not_implemented(self):
        # Cannot instantiate abstract model directly, test the method on a class basis
        with pytest.raises(NotImplementedError):
            OrderModelMixin.get_total_weight(None)

    def test_get_parcels_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            OrderModelMixin.get_parcels(None)

    def test_get_sender_address_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            OrderModelMixin.get_sender_address(None)

    def test_get_receiver_address_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            OrderModelMixin.get_receiver_address(None)


class TestShipmentModelMixin:
    def test_is_abstract(self):
        assert ShipmentModelMixin._meta.abstract is True

    def test_has_provider_field(self):
        field = ShipmentModelMixin._meta.get_field("provider")
        assert isinstance(field, django_models.CharField)
        assert field.max_length == 64

    def test_has_status_field_with_default_new(self):
        field = ShipmentModelMixin._meta.get_field("status")
        assert isinstance(field, django_models.CharField)
        assert field.default == "new"

    def test_has_external_id_field(self):
        field = ShipmentModelMixin._meta.get_field("external_id")
        assert isinstance(field, django_models.CharField)
        assert field.blank is True

    def test_has_tracking_number_field(self):
        field = ShipmentModelMixin._meta.get_field("tracking_number")
        assert isinstance(field, django_models.CharField)
        assert field.blank is True

    def test_has_label_url_field(self):
        field = ShipmentModelMixin._meta.get_field("label_url")
        assert isinstance(field, django_models.URLField)
        assert field.blank is True

    def test_has_created_at_field(self):
        field = ShipmentModelMixin._meta.get_field("created_at")
        assert isinstance(field, django_models.DateTimeField)
        assert field.auto_now_add is True

    def test_has_updated_at_field(self):
        field = ShipmentModelMixin._meta.get_field("updated_at")
        assert isinstance(field, django_models.DateTimeField)
        assert field.auto_now is True


class TestShipmentConcreteModel:
    def test_is_not_abstract(self):
        assert Shipment._meta.abstract is False

    def test_has_order_id_field(self):
        field = Shipment._meta.get_field("order_id")
        assert isinstance(field, django_models.CharField)
        assert field.max_length == 255
        assert field.db_index is True

    def test_inherits_mixin_fields(self):
        field_names = [f.name for f in Shipment._meta.get_fields()]
        assert "provider" in field_names
        assert "status" in field_names
        assert "external_id" in field_names
        assert "tracking_number" in field_names
        assert "label_url" in field_names
        assert "created_at" in field_names
        assert "updated_at" in field_names

    def test_has_swappable_meta(self):
        assert hasattr(Shipment._meta, "swappable")
        assert Shipment._meta.swappable == "SENDPARCEL_SHIPMENT_MODEL"

    def test_str_representation(self):
        shipment = Shipment(pk=42, provider="dummy", status="new")
        assert str(shipment) == "Shipment 42 (dummy: new)"
```

**Step 2: Run tests to verify they fail**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_models.py -v
```
Expected: FAIL — `ImportError` because `Shipment` does not exist in `sendparcel_django.models`, and `created_at`/`updated_at` fields are missing from `ShipmentModelMixin`.

**Step 3: Update sendparcel_django/models.py with timestamps and concrete Shipment**

Replace the entire contents of `sendparcel_django/models.py`:

```python
"""Abstract model mixins and concrete models for sendparcel."""

from __future__ import annotations

from decimal import Decimal

import swapper
from django.db import models


class OrderModelMixin(models.Model):
    """Abstract order model contract for sendparcel integrations."""

    class Meta:
        abstract = True

    def get_total_weight(self) -> Decimal:
        raise NotImplementedError

    def get_parcels(self) -> list[dict]:
        raise NotImplementedError

    def get_sender_address(self) -> dict:
        raise NotImplementedError

    def get_receiver_address(self) -> dict:
        raise NotImplementedError


class ShipmentModelMixin(models.Model):
    """Abstract shipment model contract for sendparcel integrations."""

    provider = models.CharField(max_length=64)
    status = models.CharField(max_length=32, default="new")
    external_id = models.CharField(max_length=128, blank=True, default="")
    tracking_number = models.CharField(
        max_length=128, blank=True, default=""
    )
    label_url = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Shipment(ShipmentModelMixin):
    """Default concrete shipment model. Swappable via SENDPARCEL_SHIPMENT_MODEL."""

    order_id = models.CharField(max_length=255, db_index=True)

    class Meta(ShipmentModelMixin.Meta):
        swappable = swapper.swappable_setting(
            "sendparcel_django", "Shipment"
        )

    def __str__(self) -> str:
        return f"Shipment {self.pk} ({self.provider}: {self.status})"
```

**Step 4: Run model tests to verify they pass**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_models.py -v
```
Expected: All model tests PASS.

**Step 5: Run full test suite to check for regressions**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/ -v
```
Expected: All tests pass.

**Step 6: Commit**

```bash
git add sendparcel_django/models.py tests/test_models.py
git commit -m "feat: add swappable Shipment model with timestamps"
```

---

### Task 6: Add initial migration

**Files:**
- Create: `sendparcel_django/migrations/0001_initial.py` (generated by Django)
- Create: `sendparcel_django/migrations/__init__.py` (generated by Django)

**Step 1: Generate the initial migration**

Run (from `django-sendparcel/`):
```bash
DJANGO_SETTINGS_MODULE=tests.settings uv run python -m django makemigrations sendparcel_django --name initial
```
Expected: Output like `Migrations for 'sendparcel_django': sendparcel_django/migrations/0001_initial.py - Create model Shipment`

**Step 2: Verify migration applies cleanly**

Run (from `django-sendparcel/`):
```bash
DJANGO_SETTINGS_MODULE=tests.settings uv run python -m django migrate --run-syncdb
```
Expected: Migrations apply without errors.

**Step 3: Write a test to verify migration exists and is consistent**

Add to `tests/test_models.py` at the end:

```python
@pytest.mark.django_db
class TestMigrations:
    def test_migration_is_consistent(self):
        """makemigrations --check verifies no pending model changes."""
        from django.core.management import call_command

        # Raises SystemExit(1) if migrations are out of sync
        call_command("makemigrations", "--check", "sendparcel_django")
```

**Step 4: Run the migration test**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_models.py::TestMigrations -v
```
Expected: PASS — no pending migrations.

**Step 5: Run full test suite**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/ -v
```
Expected: All tests pass.

**Step 6: Commit**

```bash
git add sendparcel_django/migrations/ tests/test_models.py
git commit -m "feat: add initial migration for Shipment model"
```

---

### Task 7: Export models from __init__.py

**Files:**
- Modify: `sendparcel_django/__init__.py`
- Test: `tests/test_exports.py`

**Step 1: Write the failing test for exports**

Create file `tests/test_exports.py`:

```python
"""Public API export tests."""


def test_order_model_mixin_is_importable():
    from sendparcel_django import OrderModelMixin

    assert OrderModelMixin._meta.abstract is True


def test_shipment_model_mixin_is_importable():
    from sendparcel_django import ShipmentModelMixin

    assert ShipmentModelMixin._meta.abstract is True


def test_shipment_is_importable():
    from sendparcel_django import Shipment

    assert Shipment._meta.abstract is False


def test_all_exports_listed_in_dunder_all():
    import sendparcel_django

    expected = {
        "DjangoOrderAdapter",
        "DjangoPluginRegistry",
        "DjangoShipmentAdapter",
        "OrderModelMixin",
        "ProviderChoiceForm",
        "Shipment",
        "ShipmentModelMixin",
        "registry",
    }
    assert set(sendparcel_django.__all__) == expected
```

**Step 2: Run tests to verify they fail**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_exports.py -v
```
Expected: FAIL — `ImportError` for `OrderModelMixin`, `ShipmentModelMixin`, `Shipment`.

**Step 3: Update sendparcel_django/__init__.py with model exports**

Replace the entire contents of `sendparcel_django/__init__.py`:

```python
"""Django adapter for sendparcel."""

default_app_config = "sendparcel_django.apps.SendparcelConfig"

from sendparcel_django.forms import ProviderChoiceForm
from sendparcel_django.models import OrderModelMixin, Shipment, ShipmentModelMixin
from sendparcel_django.protocols import (
    DjangoOrderAdapter,
    DjangoShipmentAdapter,
)
from sendparcel_django.registry import DjangoPluginRegistry, registry

__all__ = [
    "DjangoOrderAdapter",
    "DjangoPluginRegistry",
    "DjangoShipmentAdapter",
    "OrderModelMixin",
    "ProviderChoiceForm",
    "Shipment",
    "ShipmentModelMixin",
    "registry",
]
```

**Step 4: Run export tests to verify they pass**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_exports.py -v
```
Expected: All 4 tests PASS.

**Step 5: Run full test suite**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/ -v
```
Expected: All tests pass.

**Step 6: Commit**

```bash
git add sendparcel_django/__init__.py tests/test_exports.py
git commit -m "feat: export OrderModelMixin, ShipmentModelMixin, Shipment from package"
```

---

### Task 8: Fix callback view exception handling

**Files:**
- Modify: `sendparcel_django/views.py`
- Modify: `tests/test_views.py`

**Step 1: Write failing tests for new exception handling**

Add the following test functions to the end of the existing `tests/test_views.py` file. These tests use the existing `DummyShipment`, `Repo`, and `RequestStub` classes already defined in that file, but need new provider variants:

```python
from sendparcel.exceptions import (
    CommunicationError,
    InvalidTransitionError,
    SendParcelException,
)


class CommunicationErrorProvider(BaseProvider):
    slug = "comm_err"
    display_name = "CommErr"

    async def create_shipment(self, **kwargs):
        return {}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        raise CommunicationError("Provider API unreachable")

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        pass


class TransitionErrorProvider(BaseProvider):
    slug = "trans_err"
    display_name = "TransErr"

    async def create_shipment(self, **kwargs):
        return {}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        pass

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        raise InvalidTransitionError("Cannot transition from current state")


class GenericErrorProvider(BaseProvider):
    slug = "generic_err"
    display_name = "GenericErr"

    async def create_shipment(self, **kwargs):
        return {}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        pass

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        raise SendParcelException("Something went wrong")


def test_callback_returns_502_on_communication_error() -> None:
    core_registry.register(CommunicationErrorProvider)
    shipment = DummyShipment()
    shipment.provider = "comm_err"
    repo = Repo()
    repo.shipment = shipment

    response = callback(
        RequestStub({"event": "status_update"}, {}),
        "s-1",
        repository=repo,
        config={},
    )

    assert response.status_code == 502
    assert b"Provider API unreachable" in response.content


def test_callback_returns_409_on_invalid_transition() -> None:
    core_registry.register(TransitionErrorProvider)
    shipment = DummyShipment()
    shipment.provider = "trans_err"
    repo = Repo()
    repo.shipment = shipment

    response = callback(
        RequestStub({"event": "status_update"}, {}),
        "s-1",
        repository=repo,
        config={},
    )

    assert response.status_code == 409
    assert b"Cannot transition from current state" in response.content


def test_callback_returns_400_on_generic_sendparcel_exception() -> None:
    core_registry.register(GenericErrorProvider)
    shipment = DummyShipment()
    shipment.provider = "generic_err"
    repo = Repo()
    repo.shipment = shipment

    response = callback(
        RequestStub({"event": "status_update"}, {}),
        "s-1",
        repository=repo,
        config={},
    )

    assert response.status_code == 400
    assert b"Something went wrong" in response.content


def test_callback_returns_500_when_no_repository() -> None:
    response = callback(
        RequestStub({}, {}),
        "s-1",
        repository=None,
        config={},
    )

    assert response.status_code == 500
    assert b"Repository is required" in response.content
```

**Step 2: Run new tests to verify they fail**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_views.py -v
```
Expected: The new tests for 502 and 409 status codes FAIL (these exceptions are not caught). The 400 generic and 500 no-repository tests may pass because the existing code already handles some of these cases.

**Step 3: Update sendparcel_django/views.py with proper exception handling**

Replace the entire contents of `sendparcel_django/views.py`:

```python
"""Django views for callback endpoints."""

from __future__ import annotations

import json

import anyio
from django.http import HttpRequest, JsonResponse
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
)
from sendparcel.flow import ShipmentFlow


def callback(
    request: HttpRequest,
    shipment_id: str,
    *,
    repository=None,
    config: dict | None = None,
) -> JsonResponse:
    """Handle provider callbacks through the core shipment flow."""
    if repository is None:
        return JsonResponse(
            {"detail": "Repository is required for callback processing."},
            status=500,
        )

    try:
        payload = (
            json.loads(request.body.decode("utf-8"))
            if getattr(request, "body", b"")
            else {}
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON payload."}, status=400)

    flow = ShipmentFlow(repository=repository, config=config or {})

    try:
        shipment = anyio.run(
            _handle_callback,
            flow,
            repository,
            shipment_id,
            payload,
            dict(getattr(request, "headers", {})),
            getattr(request, "body", b""),
        )
    except CommunicationError as exc:
        return JsonResponse({"detail": str(exc)}, status=502)
    except InvalidTransitionError as exc:
        return JsonResponse({"detail": str(exc)}, status=409)
    except InvalidCallbackError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    except SendParcelException as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    return JsonResponse(
        {
            "shipment_id": str(shipment.id),
            "status": str(shipment.status),
            "received": True,
        }
    )


async def _handle_callback(
    flow: ShipmentFlow,
    repository,
    shipment_id: str,
    payload: dict,
    headers: dict,
    raw_body: bytes,
):
    shipment = await repository.get_by_id(shipment_id)
    return await flow.handle_callback(
        shipment,
        payload,
        headers,
        raw_body=raw_body,
    )
```

Note: The exception catch order matters — `CommunicationError`, `InvalidTransitionError`, and `InvalidCallbackError` must come before the generic `SendParcelException` since they are subclasses of it.

**Step 4: Run view tests to verify they pass**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_views.py -v
```
Expected: All view tests PASS (2 existing + 4 new = 6 total).

**Step 5: Run full test suite**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/ -v
```
Expected: All tests pass.

**Step 6: Commit**

```bash
git add sendparcel_django/views.py tests/test_views.py
git commit -m "fix: add proper exception-to-HTTP-status mapping in callback view"
```

---

### Task 9: Add DjangoShipmentRepository

**Files:**
- Create: `sendparcel_django/repository.py`
- Modify: `sendparcel_django/__init__.py`
- Test: `tests/test_repository.py`

**Step 1: Write failing tests for the repository**

Create file `tests/test_repository.py`:

```python
"""DjangoShipmentRepository tests."""

import pytest
from sendparcel.enums import ShipmentStatus

from sendparcel_django.models import Shipment
from sendparcel_django.repository import DjangoShipmentRepository


@pytest.mark.django_db
class TestDjangoShipmentRepository:
    def setup_method(self):
        self.repo = DjangoShipmentRepository()

    @pytest.mark.asyncio
    async def test_create_shipment(self):
        shipment = await self.repo.create(
            order_id="order-1",
            provider="dummy",
            status=ShipmentStatus.NEW,
        )

        assert shipment.pk is not None
        assert shipment.order_id == "order-1"
        assert shipment.provider == "dummy"
        assert shipment.status == ShipmentStatus.NEW

    @pytest.mark.asyncio
    async def test_get_by_id(self):
        created = await self.repo.create(
            order_id="order-2",
            provider="dummy",
            status=ShipmentStatus.NEW,
        )

        fetched = await self.repo.get_by_id(str(created.pk))

        assert fetched.pk == created.pk
        assert fetched.order_id == "order-2"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found_raises(self):
        with pytest.raises(Shipment.DoesNotExist):
            await self.repo.get_by_id("99999")

    @pytest.mark.asyncio
    async def test_save_persists_changes(self):
        shipment = await self.repo.create(
            order_id="order-3",
            provider="dummy",
            status=ShipmentStatus.NEW,
        )
        shipment.tracking_number = "TRACK-123"

        saved = await self.repo.save(shipment)

        fetched = await self.repo.get_by_id(str(saved.pk))
        assert fetched.tracking_number == "TRACK-123"

    @pytest.mark.asyncio
    async def test_update_status(self):
        shipment = await self.repo.create(
            order_id="order-4",
            provider="dummy",
            status=ShipmentStatus.NEW,
        )

        updated = await self.repo.update_status(
            str(shipment.pk),
            ShipmentStatus.CREATED,
            external_id="ext-99",
        )

        assert updated.status == ShipmentStatus.CREATED
        assert updated.external_id == "ext-99"

        # Verify persisted to DB
        fetched = await self.repo.get_by_id(str(shipment.pk))
        assert fetched.status == ShipmentStatus.CREATED
        assert fetched.external_id == "ext-99"

    @pytest.mark.asyncio
    async def test_create_with_order_object(self):
        """If 'order' kwarg is given, extract id from it."""

        class FakeOrder:
            id = "order-from-obj"

        shipment = await self.repo.create(
            order=FakeOrder(),
            provider="dummy",
            status=ShipmentStatus.NEW,
        )

        assert shipment.order_id == "order-from-obj"
```

**Step 2: Run tests to verify they fail**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_repository.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'sendparcel_django.repository'` (the existing `registry.py` file is different from the new `repository.py`).

**Step 3: Create sendparcel_django/repository.py**

Create file `sendparcel_django/repository.py` (note: the existing file at this path is `registry.py`, this is a **new** file `repository.py`):

```python
"""Django ORM repository for shipment persistence."""

from __future__ import annotations

from asgiref.sync import sync_to_async

import swapper


class DjangoShipmentRepository:
    """Repository wrapping Django ORM with sync_to_async."""

    def _get_model(self):
        return swapper.load_model("sendparcel_django", "Shipment")

    async def get_by_id(self, shipment_id: str):
        """Fetch a shipment by primary key."""
        model = self._get_model()
        return await sync_to_async(model.objects.get)(pk=shipment_id)

    async def create(self, **kwargs):
        """Create a new shipment record.

        Accepts an optional ``order`` keyword argument. If provided
        and ``order_id`` is not already in *kwargs*, ``order_id`` is
        derived from ``order.id``.
        """
        model = self._get_model()
        order = kwargs.pop("order", None)
        if order is not None and "order_id" not in kwargs:
            kwargs["order_id"] = str(getattr(order, "id", order))
        return await sync_to_async(model.objects.create)(**kwargs)

    async def save(self, shipment):
        """Persist changes on an existing shipment instance."""
        await sync_to_async(shipment.save)()
        return shipment

    async def update_status(self, shipment_id: str, status: str, **fields):
        """Update the status (and optional extra fields) of a shipment."""
        shipment = await self.get_by_id(shipment_id)
        shipment.status = status
        for key, value in fields.items():
            setattr(shipment, key, value)
        await sync_to_async(shipment.save)()
        return shipment
```

**Step 4: Run repository tests to verify they pass**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_repository.py -v
```
Expected: All 6 tests PASS.

**Step 5: Add DjangoShipmentRepository to __init__.py exports**

Update `sendparcel_django/__init__.py` to add the repository import and export:

Add this import line after the models import:

```python
from sendparcel_django.repository import DjangoShipmentRepository
```

And add `"DjangoShipmentRepository"` to the `__all__` list.

The full updated `sendparcel_django/__init__.py`:

```python
"""Django adapter for sendparcel."""

default_app_config = "sendparcel_django.apps.SendparcelConfig"

from sendparcel_django.forms import ProviderChoiceForm
from sendparcel_django.models import OrderModelMixin, Shipment, ShipmentModelMixin
from sendparcel_django.protocols import (
    DjangoOrderAdapter,
    DjangoShipmentAdapter,
)
from sendparcel_django.registry import DjangoPluginRegistry, registry
from sendparcel_django.repository import DjangoShipmentRepository

__all__ = [
    "DjangoOrderAdapter",
    "DjangoPluginRegistry",
    "DjangoShipmentAdapter",
    "DjangoShipmentRepository",
    "OrderModelMixin",
    "ProviderChoiceForm",
    "Shipment",
    "ShipmentModelMixin",
    "registry",
]
```

**Step 6: Update the exports test**

In `tests/test_exports.py`, update `test_all_exports_listed_in_dunder_all` to include `DjangoShipmentRepository`:

```python
def test_all_exports_listed_in_dunder_all():
    import sendparcel_django

    expected = {
        "DjangoOrderAdapter",
        "DjangoPluginRegistry",
        "DjangoShipmentAdapter",
        "DjangoShipmentRepository",
        "OrderModelMixin",
        "ProviderChoiceForm",
        "Shipment",
        "ShipmentModelMixin",
        "registry",
    }
    assert set(sendparcel_django.__all__) == expected
```

Also add a test for it:

```python
def test_django_shipment_repository_is_importable():
    from sendparcel_django import DjangoShipmentRepository

    assert DjangoShipmentRepository is not None
```

**Step 7: Run full test suite**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/ -v
```
Expected: All tests pass.

**Step 8: Commit**

```bash
git add sendparcel_django/repository.py sendparcel_django/__init__.py tests/test_repository.py tests/test_exports.py
git commit -m "feat: add DjangoShipmentRepository with sync_to_async ORM operations"
```

---

### Task 10: Complete admin with ShipmentAdmin

**Files:**
- Modify: `sendparcel_django/admin.py`
- Modify: `tests/test_admin.py`

**Step 1: Write failing tests for the new ShipmentAdmin**

Replace the entire contents of `tests/test_admin.py`:

```python
"""Admin tests."""

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory
from sendparcel.enums import ShipmentStatus
from sendparcel.fsm import create_shipment_machine

import swapper
from sendparcel_django.admin import ShipmentAdmin, build_status_actions


# --- Legacy build_status_actions tests (backward compat) ---


class FakeShipment:
    """Minimal shipment for non-DB admin action tests."""

    def __init__(self, status: str) -> None:
        self.status = status


def test_mark_in_transit_action_changes_status() -> None:
    shipment = FakeShipment(ShipmentStatus.LABEL_READY)
    create_shipment_machine(shipment)
    actions = build_status_actions()

    actions["mark_in_transit"]([shipment])

    assert shipment.status == ShipmentStatus.IN_TRANSIT


def test_cancel_action_changes_status() -> None:
    shipment = FakeShipment(ShipmentStatus.CREATED)
    create_shipment_machine(shipment)
    actions = build_status_actions()

    actions["cancel"]([shipment])

    assert shipment.status == ShipmentStatus.CANCELLED


# --- ShipmentAdmin registration tests ---


def test_shipment_admin_is_registered():
    model = swapper.load_model("sendparcel_django", "Shipment")
    assert model in admin.site._registry
    assert isinstance(admin.site._registry[model], ShipmentAdmin)


def test_shipment_admin_list_display():
    model = swapper.load_model("sendparcel_django", "Shipment")
    model_admin = admin.site._registry[model]
    expected_fields = (
        "id",
        "order_id",
        "status",
        "provider",
        "tracking_number",
        "label_url",
        "created_at",
    )
    assert model_admin.list_display == expected_fields


def test_shipment_admin_list_filter():
    model = swapper.load_model("sendparcel_django", "Shipment")
    model_admin = admin.site._registry[model]
    assert "status" in model_admin.list_filter
    assert "provider" in model_admin.list_filter


def test_shipment_admin_search_fields():
    model = swapper.load_model("sendparcel_django", "Shipment")
    model_admin = admin.site._registry[model]
    assert "tracking_number" in model_admin.search_fields
    assert "external_id" in model_admin.search_fields
    assert "order_id" in model_admin.search_fields


def test_shipment_admin_readonly_fields():
    model = swapper.load_model("sendparcel_django", "Shipment")
    model_admin = admin.site._registry[model]
    assert "external_id" in model_admin.readonly_fields
    assert "tracking_number" in model_admin.readonly_fields
    assert "label_url" in model_admin.readonly_fields
    assert "created_at" in model_admin.readonly_fields
    assert "updated_at" in model_admin.readonly_fields


# --- ShipmentAdmin action tests (with real DB) ---


@pytest.fixture
def shipment_model():
    return swapper.load_model("sendparcel_django", "Shipment")


@pytest.fixture
def model_admin():
    model = swapper.load_model("sendparcel_django", "Shipment")
    return admin.site._registry[model]


@pytest.fixture
def admin_request():
    factory = RequestFactory()
    request = factory.get("/admin/")
    request.user = User(username="admin", is_staff=True, is_superuser=True)
    # MessageMiddleware stores messages on the request
    from django.contrib.messages.storage.fallback import FallbackStorage

    setattr(request, "session", "session")
    setattr(request, "_messages", FallbackStorage(request))
    return request


@pytest.mark.django_db
def test_admin_action_mark_in_transit(
    shipment_model, model_admin, admin_request
):
    shipment = shipment_model.objects.create(
        order_id="o-1",
        provider="dummy",
        status=ShipmentStatus.LABEL_READY,
    )

    queryset = shipment_model.objects.filter(pk=shipment.pk)
    model_admin.mark_in_transit(admin_request, queryset)

    shipment.refresh_from_db()
    assert shipment.status == ShipmentStatus.IN_TRANSIT


@pytest.mark.django_db
def test_admin_action_mark_delivered(
    shipment_model, model_admin, admin_request
):
    shipment = shipment_model.objects.create(
        order_id="o-2",
        provider="dummy",
        status=ShipmentStatus.IN_TRANSIT,
    )

    queryset = shipment_model.objects.filter(pk=shipment.pk)
    model_admin.mark_delivered(admin_request, queryset)

    shipment.refresh_from_db()
    assert shipment.status == ShipmentStatus.DELIVERED


@pytest.mark.django_db
def test_admin_action_cancel(shipment_model, model_admin, admin_request):
    shipment = shipment_model.objects.create(
        order_id="o-3",
        provider="dummy",
        status=ShipmentStatus.CREATED,
    )

    queryset = shipment_model.objects.filter(pk=shipment.pk)
    model_admin.cancel_shipment(admin_request, queryset)

    shipment.refresh_from_db()
    assert shipment.status == ShipmentStatus.CANCELLED


@pytest.mark.django_db
def test_admin_action_skips_invalid_transition(
    shipment_model, model_admin, admin_request
):
    """Action on a shipment in wrong state should not change it."""
    shipment = shipment_model.objects.create(
        order_id="o-4",
        provider="dummy",
        status=ShipmentStatus.DELIVERED,
    )

    queryset = shipment_model.objects.filter(pk=shipment.pk)
    model_admin.mark_in_transit(admin_request, queryset)

    shipment.refresh_from_db()
    # Status should not change because DELIVERED -> IN_TRANSIT is invalid
    assert shipment.status == ShipmentStatus.DELIVERED
```

**Step 2: Run tests to verify they fail**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_admin.py -v
```
Expected: FAIL — `ImportError` because `ShipmentAdmin` does not exist in `sendparcel_django.admin`.

**Step 3: Replace sendparcel_django/admin.py with complete ShipmentAdmin**

Replace the entire contents of `sendparcel_django/admin.py`:

```python
"""Admin integration for sendparcel."""

from __future__ import annotations

import warnings
from collections.abc import Callable, Iterable

import swapper
from django.contrib import admin
from sendparcel.fsm import create_shipment_machine


def _transition(shipment, trigger_name: str) -> bool:
    """Attempt a single FSM transition on a shipment instance."""
    create_shipment_machine(shipment)
    may_trigger = getattr(shipment, "may_trigger", None)
    trigger = getattr(shipment, trigger_name, None)
    if may_trigger is None or trigger is None:
        return False
    if not may_trigger(trigger_name):
        return False
    trigger()
    return True


def build_status_actions() -> dict[str, Callable[[Iterable], int]]:
    """Create reusable bulk actions for shipment status transitions.

    .. deprecated::
        Use :class:`ShipmentAdmin` instead which registers all actions
        as proper Django admin actions.
    """
    warnings.warn(
        "build_status_actions() is deprecated. "
        "Use ShipmentAdmin with its built-in actions instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    def mark_in_transit(shipments: Iterable) -> int:
        return sum(_transition(s, "mark_in_transit") for s in shipments)

    def cancel(shipments: Iterable) -> int:
        return sum(_transition(s, "cancel") for s in shipments)

    return {
        "mark_in_transit": mark_in_transit,
        "cancel": cancel,
    }


def _get_shipment_model():
    return swapper.load_model("sendparcel_django", "Shipment")


class ShipmentAdmin(admin.ModelAdmin):
    """Full ModelAdmin for the (swappable) Shipment model."""

    list_display = (
        "id",
        "order_id",
        "status",
        "provider",
        "tracking_number",
        "label_url",
        "created_at",
    )
    list_filter = ("status", "provider")
    search_fields = ("tracking_number", "external_id", "order_id")
    readonly_fields = (
        "external_id",
        "tracking_number",
        "label_url",
        "created_at",
        "updated_at",
    )

    actions = ["mark_in_transit", "mark_delivered", "cancel_shipment"]

    @admin.action(description="Mark selected as in transit")
    def mark_in_transit(self, request, queryset):
        count = 0
        for shipment in queryset:
            if _transition(shipment, "mark_in_transit"):
                shipment.save()
                count += 1
        self.message_user(
            request, f"{count} shipment(s) marked as in transit."
        )

    @admin.action(description="Mark selected as delivered")
    def mark_delivered(self, request, queryset):
        count = 0
        for shipment in queryset:
            if _transition(shipment, "mark_delivered"):
                shipment.save()
                count += 1
        self.message_user(
            request, f"{count} shipment(s) marked as delivered."
        )

    @admin.action(description="Cancel selected shipments")
    def cancel_shipment(self, request, queryset):
        count = 0
        for shipment in queryset:
            if _transition(shipment, "cancel"):
                shipment.save()
                count += 1
        self.message_user(
            request, f"{count} shipment(s) cancelled."
        )


# Register the (possibly swapped) Shipment model with ShipmentAdmin.
try:
    admin.site.register(_get_shipment_model(), ShipmentAdmin)
except admin.sites.AlreadyRegistered:
    pass
```

**Step 4: Run admin tests to verify they pass**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_admin.py -v
```
Expected: All admin tests PASS.

Note: The two legacy `build_status_actions` tests now trigger a `DeprecationWarning`. If pytest is configured to treat warnings as errors, the tests may fail. In that case, add `filterwarnings = ["ignore::DeprecationWarning:tests.test_admin"]` to `pyproject.toml` under `[tool.pytest.ini_options]`, or update the two legacy tests to use `pytest.warns(DeprecationWarning)`:

```python
def test_mark_in_transit_action_changes_status() -> None:
    shipment = FakeShipment(ShipmentStatus.LABEL_READY)
    create_shipment_machine(shipment)
    with pytest.warns(DeprecationWarning, match="build_status_actions"):
        actions = build_status_actions()

    actions["mark_in_transit"]([shipment])

    assert shipment.status == ShipmentStatus.IN_TRANSIT


def test_cancel_action_changes_status() -> None:
    shipment = FakeShipment(ShipmentStatus.CREATED)
    create_shipment_machine(shipment)
    with pytest.warns(DeprecationWarning, match="build_status_actions"):
        actions = build_status_actions()

    actions["cancel"]([shipment])

    assert shipment.status == ShipmentStatus.CANCELLED
```

**Step 5: Run full test suite**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/ -v
```
Expected: All tests pass.

**Step 6: Commit**

```bash
git add sendparcel_django/admin.py tests/test_admin.py
git commit -m "feat: add ShipmentAdmin with full list_display, filters, and FSM actions"
```

---

### Task 11: Fix registry — remove get_callback_paths()

**Files:**
- Modify: `sendparcel_django/registry.py`
- Modify: `tests/test_registry.py`

The `get_callback_paths()` method returns raw string templates like `"callback/fake/"` which are not actual Django URL pattern objects and not useful. The real URL routing is handled by `sendparcel_django/urls.py`. This method should be removed.

**Step 1: Update the registry test to remove the callback paths test and add more useful tests**

Replace the entire contents of `tests/test_registry.py`:

```python
"""Registry wrapper tests."""

from sendparcel.provider import BaseProvider
from sendparcel_django.registry import DjangoPluginRegistry


class FakeProvider(BaseProvider):
    slug = "fake"
    display_name = "Fake"

    async def create_shipment(self, **kwargs):
        return {}


class AnotherProvider(BaseProvider):
    slug = "another"
    display_name = "Another"

    async def create_shipment(self, **kwargs):
        return {}


def test_register_and_get_by_slug():
    reg = DjangoPluginRegistry()
    reg.register(FakeProvider)

    assert reg.get_by_slug("fake") is FakeProvider


def test_get_choices_returns_slug_display_pairs():
    reg = DjangoPluginRegistry()
    reg.register(FakeProvider)
    reg.register(AnotherProvider)

    choices = reg.get_choices()

    assert ("fake", "Fake") in choices
    assert ("another", "Another") in choices


def test_inherits_from_core_plugin_registry():
    from sendparcel.registry import PluginRegistry

    assert issubclass(DjangoPluginRegistry, PluginRegistry)


def test_unregister_removes_provider():
    reg = DjangoPluginRegistry()
    reg.register(FakeProvider)
    reg.unregister("fake")

    import pytest

    with pytest.raises(KeyError):
        reg.get_by_slug("fake")
```

**Step 2: Run the tests to verify the old callback paths test is gone**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_registry.py -v
```
Expected: The new tests pass. There should be 4 tests.

**Step 3: Remove get_callback_paths() from the registry**

Replace the entire contents of `sendparcel_django/registry.py`:

```python
"""Django-specific registry wrapper."""

from sendparcel.registry import PluginRegistry


class DjangoPluginRegistry(PluginRegistry):
    """Plugin registry with Django integration.

    URL routing for callbacks is handled by ``sendparcel_django.urls``.
    """


registry = DjangoPluginRegistry()
```

**Step 4: Run registry tests again to verify they still pass**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/test_registry.py -v
```
Expected: All 4 tests PASS.

**Step 5: Run full test suite to check for regressions**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/ -v
```
Expected: All tests pass. No other code depends on `get_callback_paths()`.

**Step 6: Commit**

```bash
git add sendparcel_django/registry.py tests/test_registry.py
git commit -m "refactor: remove half-baked get_callback_paths() from registry"
```

---

### Task 12: Final verification — full test suite and ruff lint

**Files:** (none — verification only)

**Step 1: Run the complete test suite**

Run (from `django-sendparcel/`):
```bash
uv run pytest tests/ -v
```
Expected: All tests pass (approximately 30+ tests across all test files).

**Step 2: Run ruff linter**

Run (from `django-sendparcel/`):
```bash
uv run ruff check sendparcel_django/ tests/
```
Expected: No lint errors. If there are any, fix them.

**Step 3: Run ruff formatter check**

Run (from `django-sendparcel/`):
```bash
uv run ruff format --check sendparcel_django/ tests/
```
Expected: All files formatted correctly. If not, run `uv run ruff format sendparcel_django/ tests/` and commit the formatting changes.

**Step 4: Verify migration consistency one more time**

Run (from `django-sendparcel/`):
```bash
DJANGO_SETTINGS_MODULE=tests.settings uv run python -m django makemigrations --check sendparcel_django
```
Expected: `No changes detected in app 'sendparcel_django'.`

**Step 5: Commit any final fixes**

If any lint/format fixes were needed:
```bash
git add -A
git commit -m "style: fix lint and formatting issues"
```

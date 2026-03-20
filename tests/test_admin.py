"""Admin tests."""

from __future__ import annotations

from typing import Any, cast

import pytest
import swapper
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.base import SessionBase
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory
from sendparcel.enums import ShipmentStatus
from sendparcel_django.admin import ShipmentAdmin, build_status_actions


def _shipment_model() -> Any:
    model = swapper.load_model("sendparcel_django", "Shipment")
    assert model is not None
    return model


# --- Legacy build_status_actions tests (backward compat) ---


class FakeShipment:
    """Minimal shipment for non-DB admin action tests."""

    def __init__(self, status: str, tracking_number: str = "") -> None:
        self.status = status
        self.tracking_number = tracking_number


def test_mark_in_transit_action_changes_status() -> None:
    shipment = FakeShipment(
        ShipmentStatus.LABEL_READY, tracking_number="TRK-TEST"
    )
    with pytest.warns(DeprecationWarning, match="build_status_actions"):
        actions = build_status_actions()

    actions["mark_in_transit"]([shipment])

    assert shipment.status == ShipmentStatus.IN_TRANSIT


def test_cancel_action_changes_status() -> None:
    shipment = FakeShipment(ShipmentStatus.CREATED)
    with pytest.warns(DeprecationWarning, match="build_status_actions"):
        actions = build_status_actions()

    actions["cancel"]([shipment])

    assert shipment.status == ShipmentStatus.CANCELLED


# --- ShipmentAdmin registration tests ---


def test_shipment_admin_is_registered() -> None:
    model = _shipment_model()
    assert model in admin.site._registry
    assert isinstance(admin.site._registry[model], ShipmentAdmin)


def test_shipment_admin_list_display() -> None:
    model = _shipment_model()
    model_admin = admin.site._registry[model]
    expected_fields = (
        "id",
        "reference_id",
        "status",
        "provider",
        "tracking_number",
        "created_at",
    )
    assert model_admin.list_display == expected_fields


def test_shipment_admin_list_filter() -> None:
    model = _shipment_model()
    model_admin = admin.site._registry[model]
    assert "status" in model_admin.list_filter
    assert "provider" in model_admin.list_filter


def test_shipment_admin_search_fields() -> None:
    model = _shipment_model()
    model_admin = admin.site._registry[model]
    assert "tracking_number" in model_admin.search_fields
    assert "external_id" in model_admin.search_fields
    assert "reference_id" in model_admin.search_fields


def test_shipment_admin_readonly_fields() -> None:
    model = _shipment_model()
    model_admin = admin.site._registry[model]
    assert "external_id" in model_admin.readonly_fields
    assert "tracking_number" in model_admin.readonly_fields
    assert "created_at" in model_admin.readonly_fields
    assert "updated_at" in model_admin.readonly_fields


# --- ShipmentAdmin action tests (with real DB) ---


@pytest.fixture
def shipment_model() -> Any:
    return _shipment_model()


@pytest.fixture
def model_admin() -> Any:
    model = _shipment_model()
    return admin.site._registry[model]


@pytest.fixture
def admin_request() -> Any:
    factory = RequestFactory()
    request = factory.get("/admin/")
    request.user = User(username="admin", is_staff=True, is_superuser=True)
    # MessageMiddleware stores messages on the request
    request.session = cast(SessionBase, SessionStore())
    request._messages = FallbackStorage(request)  # type: ignore[attr-defined]
    return request


@pytest.mark.django_db
def test_admin_action_mark_in_transit(
    shipment_model: Any, model_admin: Any, admin_request: Any
) -> None:
    shipment = shipment_model.objects.create(
        reference_id="o-1",
        provider="dummy",
        status=ShipmentStatus.LABEL_READY,
        tracking_number="TRK-001",
    )

    queryset = shipment_model.objects.filter(pk=shipment.pk)
    model_admin.mark_in_transit(admin_request, queryset)

    shipment.refresh_from_db()
    assert shipment.status == ShipmentStatus.IN_TRANSIT


@pytest.mark.django_db
def test_admin_action_mark_delivered(
    shipment_model: Any, model_admin: Any, admin_request: Any
) -> None:
    shipment = shipment_model.objects.create(
        reference_id="o-2",
        provider="dummy",
        status=ShipmentStatus.IN_TRANSIT,
        tracking_number="TRK-002",
    )

    queryset = shipment_model.objects.filter(pk=shipment.pk)
    model_admin.mark_delivered(admin_request, queryset)

    shipment.refresh_from_db()
    assert shipment.status == ShipmentStatus.DELIVERED


@pytest.mark.django_db
def test_admin_action_cancel(
    shipment_model: Any, model_admin: Any, admin_request: Any
) -> None:
    shipment = shipment_model.objects.create(
        reference_id="o-3",
        provider="dummy",
        status=ShipmentStatus.CREATED,
    )

    queryset = shipment_model.objects.filter(pk=shipment.pk)
    model_admin.cancel_shipment(admin_request, queryset)

    shipment.refresh_from_db()
    assert shipment.status == ShipmentStatus.CANCELLED


@pytest.mark.django_db
def test_admin_action_skips_invalid_transition(
    shipment_model: Any, model_admin: Any, admin_request: Any
) -> None:
    """Action on a shipment in wrong state should not change it."""
    shipment = shipment_model.objects.create(
        reference_id="o-4",
        provider="dummy",
        status=ShipmentStatus.DELIVERED,
    )

    queryset = shipment_model.objects.filter(pk=shipment.pk)
    model_admin.mark_in_transit(admin_request, queryset)

    shipment.refresh_from_db()
    # Status should not change because DELIVERED -> IN_TRANSIT is invalid
    assert shipment.status == ShipmentStatus.DELIVERED

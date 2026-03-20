"""Model tests."""

import pytest
from django.core.exceptions import FieldDoesNotExist
from django.db import models as django_models
from sendparcel_django.models import (
    CallbackRetry,
    Shipment,
    ShipmentModelMixin,
)


class TestShipmentModelMixin:
    def test_is_abstract(self) -> None:
        assert ShipmentModelMixin._meta.abstract is True

    def test_has_provider_field(self) -> None:
        field = ShipmentModelMixin._meta.get_field("provider")
        assert isinstance(field, django_models.CharField)
        assert field.max_length == 64

    def test_has_status_field_with_default_new(self) -> None:
        field = ShipmentModelMixin._meta.get_field("status")
        assert isinstance(field, django_models.CharField)
        assert field.default == "new"

    def test_has_external_id_field(self) -> None:
        field = ShipmentModelMixin._meta.get_field("external_id")
        assert isinstance(field, django_models.CharField)
        assert field.blank is True

    def test_has_tracking_number_field(self) -> None:
        field = ShipmentModelMixin._meta.get_field("tracking_number")
        assert isinstance(field, django_models.CharField)
        assert field.blank is True

    def test_does_not_have_label_url_field(self) -> None:
        with pytest.raises(FieldDoesNotExist):
            field_name = "label_url"
            Shipment._meta.get_field(field_name)

    def test_has_created_at_field(self) -> None:
        field = ShipmentModelMixin._meta.get_field("created_at")
        assert isinstance(field, django_models.DateTimeField)
        assert field.auto_now_add is True

    def test_has_updated_at_field(self) -> None:
        field = ShipmentModelMixin._meta.get_field("updated_at")
        assert isinstance(field, django_models.DateTimeField)
        assert field.auto_now is True


class TestShipmentConcreteModel:
    def test_is_not_abstract(self) -> None:
        assert Shipment._meta.abstract is False

    def test_has_reference_id_field(self) -> None:
        field = Shipment._meta.get_field("reference_id")
        assert isinstance(field, django_models.CharField)
        assert field.max_length == 255
        assert field.blank is True

    def test_inherits_mixin_fields(self) -> None:
        field_names = [f.name for f in Shipment._meta.get_fields()]
        assert "provider" in field_names
        assert "status" in field_names
        assert "external_id" in field_names
        assert "tracking_number" in field_names
        assert "label_url" not in field_names
        assert "created_at" in field_names
        assert "updated_at" in field_names

    def test_has_swappable_meta(self) -> None:
        assert hasattr(Shipment._meta, "swappable")
        assert Shipment._meta.swappable == "SENDPARCEL_DJANGO_SHIPMENT_MODEL"

    def test_str_representation(self) -> None:
        shipment = Shipment(pk=42, provider="dummy", status="new")
        assert str(shipment) == "Shipment 42 (dummy: new)"


@pytest.mark.django_db
class TestMigrations:
    def test_migration_is_consistent(self) -> None:
        """makemigrations --check verifies no pending model changes."""
        from django.core.management import call_command

        # Raises SystemExit(1) if migrations are out of sync
        call_command("makemigrations", "--check", "sendparcel_django")


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

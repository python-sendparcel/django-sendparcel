"""Model tests."""

import pytest
from django.db import models as django_models
from sendparcel_django.models import (
    OrderModelMixin,
    Shipment,
    ShipmentModelMixin,
)


class TestOrderModelMixin:
    def test_is_abstract(self):
        assert OrderModelMixin._meta.abstract is True

    def test_get_total_weight_raises_not_implemented(self):
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
        assert Shipment._meta.swappable == "SENDPARCEL_DJANGO_SHIPMENT_MODEL"

    def test_str_representation(self):
        shipment = Shipment(pk=42, provider="dummy", status="new")
        assert str(shipment) == "Shipment 42 (dummy: new)"

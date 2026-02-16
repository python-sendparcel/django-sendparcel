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

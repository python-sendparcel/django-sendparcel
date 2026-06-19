"""Public API export tests."""


def test_shipment_model_mixin_is_importable() -> None:
    from sendparcel_django import ShipmentModelMixin

    assert ShipmentModelMixin._meta.abstract is True


def test_shipment_is_importable() -> None:
    from sendparcel_django import Shipment

    assert Shipment._meta.abstract is False


def test_all_exports_listed_in_dunder_all() -> None:
    import sendparcel_django

    expected = {
        "DjangoShipmentRepository",
        "ProviderChoiceForm",
        "Shipment",
        "ShipmentModelMixin",
        "__version__",
        "registry",
    }
    assert set(sendparcel_django.__all__) == expected


def test_django_shipment_repository_is_importable() -> None:
    from sendparcel_django import DjangoShipmentRepository

    assert DjangoShipmentRepository is not None

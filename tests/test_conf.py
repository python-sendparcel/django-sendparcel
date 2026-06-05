"""Settings integration tests."""

from django.test import override_settings
from sendparcel_django.conf import get_settings


def test_defaults_when_no_settings_defined() -> None:
    """All settings return defaults when not set in Django settings."""
    conf = get_settings()
    assert conf.PROVIDER_SETTINGS == {}
    assert conf.DEFAULT_PROVIDER == ""
    assert conf.SHIPMENT_MODEL == "sendparcel_django.Shipment"


@override_settings(
    SENDPARCEL_PROVIDER_SETTINGS={"dummy": {"api_key": "abc123"}},
    SENDPARCEL_DEFAULT_PROVIDER="dummy",
    SENDPARCEL_DJANGO_SHIPMENT_MODEL="myapp.CustomShipment",
)
def test_settings_override_from_django_settings() -> None:
    """Settings are read from Django settings when defined."""
    conf = get_settings()
    assert conf.PROVIDER_SETTINGS == {"dummy": {"api_key": "abc123"}}
    assert conf.DEFAULT_PROVIDER == "dummy"
    assert conf.SHIPMENT_MODEL == "myapp.CustomShipment"


def test_get_settings_returns_fresh_values_each_call() -> None:
    """get_settings() reads current Django settings (not cached)."""
    conf1 = get_settings()
    assert conf1.DEFAULT_PROVIDER == ""

    with override_settings(SENDPARCEL_DEFAULT_PROVIDER="inpost"):
        conf2 = get_settings()
        assert conf2.DEFAULT_PROVIDER == "inpost"

    conf3 = get_settings()
    assert conf3.DEFAULT_PROVIDER == ""

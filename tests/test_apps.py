"""AppConfig tests."""

from unittest.mock import patch

from django.apps import apps


def test_appconfig_exists_and_has_correct_name() -> None:
    config = apps.get_app_config("sendparcel_django")
    assert config.name == "sendparcel_django"


def test_appconfig_has_correct_verbose_name() -> None:
    config = apps.get_app_config("sendparcel_django")
    assert config.verbose_name == "SendParcel"


def test_appconfig_has_correct_default_auto_field() -> None:
    config = apps.get_app_config("sendparcel_django")
    assert config.default_auto_field == "django.db.models.BigAutoField"


def test_appconfig_ready_calls_registry_discover() -> None:
    config = apps.get_app_config("sendparcel_django")
    with patch("sendparcel_django.registry.registry.discover") as mock_discover:
        config.ready()
        mock_discover.assert_called_once()

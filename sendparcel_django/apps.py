"""Django AppConfig for sendparcel."""

from django.apps import AppConfig


class SendparcelConfig(AppConfig):
    name = "sendparcel_django"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "SendParcel"

    def ready(self):
        # Inline import: avoid circular import during app init
        from sendparcel_django.registry import registry

        registry.discover()

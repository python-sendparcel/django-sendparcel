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

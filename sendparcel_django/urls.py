"""URL declarations for django-sendparcel."""

from django.urls import path

from sendparcel_django.health import HealthCheckView
from sendparcel_django.views import callback

app_name = "sendparcel_django"

urlpatterns = [
    path("callback/<str:shipment_id>/", callback, name="callback"),
    path("health/", HealthCheckView.as_view(), name="health"),
]

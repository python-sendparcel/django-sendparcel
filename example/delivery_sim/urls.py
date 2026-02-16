"""URL patterns for the delivery simulator."""

from django.urls import path

from delivery_sim import views

app_name = "delivery_sim"

urlpatterns = [
    path("", views.gateway, name="gateway"),
    path(
        "trigger/<int:shipment_id>/",
        views.trigger_status,
        name="trigger_status",
    ),
    path(
        "label/<str:shipment_id>.pdf",
        views.label_pdf,
        name="label_pdf",
    ),
]

"""URL patterns for the delivery simulator."""

from django.urls import path

from delivery_sim import views

app_name = "delivery_sim"

urlpatterns = [
    path(
        "panel/<int:shipment_id>/",
        views.sim_panel,
        name="panel",
    ),
    path(
        "advance/<int:shipment_id>/",
        views.sim_advance,
        name="advance",
    ),
    path(
        "label/<str:shipment_id>.pdf",
        views.label_pdf,
        name="label_pdf",
    ),
]

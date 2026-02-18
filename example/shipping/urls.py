"""URL patterns for the shipping example app."""

from django.urls import path

from shipping import views

app_name = "shipping"

urlpatterns = [
    path("", views.shipment_list, name="shipment_list"),
    path(
        "shipment/new/",
        views.shipment_create,
        name="shipment_create",
    ),
    path(
        "shipment/<int:pk>/",
        views.shipment_detail,
        name="shipment_detail",
    ),
    path(
        "shipment/<int:pk>/create-label/",
        views.shipment_create_label,
        name="shipment_create_label",
    ),
    path(
        "shipment/<int:pk>/refresh-status/",
        views.shipment_refresh_status,
        name="shipment_refresh_status",
    ),
]

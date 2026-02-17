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
        "shipment/<int:pk>/tracking/",
        views.shipment_tracking,
        name="shipment_tracking",
    ),
]

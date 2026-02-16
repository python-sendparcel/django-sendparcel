"""URL patterns for the shipping example app."""

from django.urls import path

from shipping import views

app_name = "shipping"

urlpatterns = [
    path("", views.order_list, name="order_list"),
    path(
        "order/new/",
        views.order_create,
        name="order_create",
    ),
    path(
        "order/<int:pk>/",
        views.order_detail,
        name="order_detail",
    ),
    path(
        "order/<int:order_pk>/ship/",
        views.create_shipment,
        name="create_shipment",
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

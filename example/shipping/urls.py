"""URL patterns for the shipping example app."""

from django.urls import path

from shipping import views

app_name = "shipping"

urlpatterns = [
    path("", views.order_list, name="order_list"),
    path(
        "zamowienie/nowe/",
        views.order_create,
        name="order_create",
    ),
    path(
        "zamowienie/<int:pk>/",
        views.order_detail,
        name="order_detail",
    ),
    path(
        "zamowienie/<int:order_pk>/wyslij/",
        views.create_shipment,
        name="create_shipment",
    ),
    path(
        "przesylka/<int:pk>/",
        views.shipment_detail,
        name="shipment_detail",
    ),
    path(
        "przesylka/<int:pk>/tracking/",
        views.shipment_tracking,
        name="shipment_tracking",
    ),
]

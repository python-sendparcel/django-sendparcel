"""Root URL configuration for the example project."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sendparcel/", include("sendparcel_django.urls")),
    path("delivery-sim/", include("delivery_sim.urls")),
    path("", include("shipping.urls")),
]

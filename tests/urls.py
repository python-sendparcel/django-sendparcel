"""URL configuration for django-sendparcel test suite."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sendparcel/", include("sendparcel_django.urls")),
]

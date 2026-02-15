"""Shared fixtures for django-sendparcel tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from django.conf import settings
from sendparcel.registry import registry as core_registry
from sendparcel_django.registry import registry as django_registry

if not settings.configured:
    settings.configure(
        DEFAULT_CHARSET="utf-8",
        USE_I18N=False,
        SECRET_KEY="test-key",
    )


@pytest.fixture(autouse=True)
def isolate_registries() -> Iterator[None]:
    """Reset global registries between tests."""
    core_old = dict(core_registry._providers)
    core_discovered = core_registry._discovered
    django_old = dict(django_registry._providers)
    django_discovered = django_registry._discovered

    core_registry._providers = {}
    core_registry._discovered = True
    django_registry._providers = {}
    django_registry._discovered = True

    try:
        yield
    finally:
        core_registry._providers = core_old
        core_registry._discovered = core_discovered
        django_registry._providers = django_old
        django_registry._discovered = django_discovered

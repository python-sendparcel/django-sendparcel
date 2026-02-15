"""Django example app tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from sendparcel.providers.dummy import DummyProvider
from sendparcel.registry import registry


def _load_example_module():
    path = Path(__file__).resolve().parents[1] / "examples" / "app.py"
    spec = importlib.util.spec_from_file_location(
        "django_sendparcel_example",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load Django example app module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_example_app_uses_builtin_dummy_provider() -> None:
    module = _load_example_module()

    assert DummyProvider.slug == module.DEFAULT_PROVIDER
    assert registry.get_by_slug("dummy") is DummyProvider

    shipment_id = module.seed_shipment()
    response = module.callback_endpoint(
        module.RequestStub(
            {"status": "in_transit"},
            {"x-dummy-token": "dummy-token"},
        ),
        shipment_id,
    )

    assert response.status_code == 200
    assert b'"status": "in_transit"' in response.content

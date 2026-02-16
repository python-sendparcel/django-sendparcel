"""Django example app tests."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from django.test import RequestFactory
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

    rf = RequestFactory()
    page = module.index(rf.get("/"))
    page_html = page.content.decode("utf-8")

    assert page.status_code == 200
    assert "tabler.min.css" in page_html
    assert 'name="provider"' in page_html
    assert 'name="recipient_email"' in page_html
    assert 'name="sender_email"' in page_html
    assert 'name="package_size"' in page_html
    assert "dummy" in page_html

    checkout = module.checkout(
        rf.post(
            "/checkout",
            data={
                "provider": "dummy",
                "recipient_email": "alice@example.com",
                "recipient_phone": "+48123456789",
                "recipient_address": "Main Street 1",
                "recipient_locker": "",
                "sender_email": "shop@example.com",
                "package_size": "M",
                "insurance": "1",
                "insurance_amount": "120",
            },
        )
    )
    checkout_html = checkout.content.decode("utf-8")
    assert checkout.status_code == 200
    assert "DummyPay simulator" in checkout_html

    pay_match = re.search(r'action="(/pay/([^"]+))"', checkout_html)
    assert pay_match is not None
    payment = module.pay(rf.post(pay_match.group(1)), pay_match.group(2))
    payment_html = payment.content.decode("utf-8")
    assert payment.status_code == 200
    assert "Download label PDF" in payment_html

    label_match = re.search(r'href="(/label/([^"]+)\.pdf)"', payment_html)
    assert label_match is not None
    label = module.label_pdf(rf.get(label_match.group(1)), label_match.group(2))
    assert label.status_code == 200
    assert label["Content-Type"] == "application/pdf"
    assert label.content.startswith(b"%PDF-")

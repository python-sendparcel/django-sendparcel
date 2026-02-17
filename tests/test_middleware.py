"""Exception middleware tests."""

from __future__ import annotations

import json

from django.http import HttpRequest, HttpResponse
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
    ShipmentNotFoundError,
)
from sendparcel_django.middleware import SendParcelExceptionMiddleware


def _make_middleware(
    response: HttpResponse | None = None,
) -> SendParcelExceptionMiddleware:
    """Create middleware with a dummy get_response."""

    def get_response(request: HttpRequest) -> HttpResponse:
        return response or HttpResponse("ok")

    return SendParcelExceptionMiddleware(get_response)


def _parse_json(response: HttpResponse) -> dict:
    return json.loads(response.content.decode("utf-8"))


class TestSendParcelExceptionMiddleware:
    def test_communication_error_returns_502(self) -> None:
        middleware = _make_middleware()
        request = HttpRequest()
        exc = CommunicationError("Provider timeout")

        response = middleware.process_exception(request, exc)

        assert response is not None
        assert response.status_code == 502
        body = _parse_json(response)
        assert body["code"] == "communication_error"
        assert "Provider timeout" in body["detail"]

    def test_invalid_callback_error_returns_400(self) -> None:
        middleware = _make_middleware()
        request = HttpRequest()
        exc = InvalidCallbackError("Bad signature")

        response = middleware.process_exception(request, exc)

        assert response is not None
        assert response.status_code == 400
        body = _parse_json(response)
        assert body["code"] == "invalid_callback"
        assert "Bad signature" in body["detail"]

    def test_invalid_transition_error_returns_409(self) -> None:
        middleware = _make_middleware()
        request = HttpRequest()
        exc = InvalidTransitionError("Cannot cancel delivered shipment")

        response = middleware.process_exception(request, exc)

        assert response is not None
        assert response.status_code == 409
        body = _parse_json(response)
        assert body["code"] == "invalid_transition"
        assert "Cannot cancel" in body["detail"]

    def test_generic_sendparcel_exception_returns_400(self) -> None:
        middleware = _make_middleware()
        request = HttpRequest()
        exc = SendParcelException("Something went wrong")

        response = middleware.process_exception(request, exc)

        assert response is not None
        assert response.status_code == 400
        body = _parse_json(response)
        assert body["code"] == "sendparcel_error"

    def test_non_sendparcel_exception_returns_none(self) -> None:
        middleware = _make_middleware()
        request = HttpRequest()
        exc = ValueError("unrelated error")

        response = middleware.process_exception(request, exc)

        assert response is None

    def test_normal_response_passes_through(self) -> None:
        expected = HttpResponse("hello", status=200)
        middleware = _make_middleware(response=expected)
        request = HttpRequest()

        response = middleware(request)

        assert response.status_code == 200
        assert response.content == b"hello"

    def test_exception_context_not_leaked(self) -> None:
        """Sensitive context from exception should not appear in response."""
        middleware = _make_middleware()
        request = HttpRequest()
        exc = CommunicationError(
            "API error",
            context={"api_key": "secret-123"},
        )

        response = middleware.process_exception(request, exc)

        assert response is not None
        body = _parse_json(response)
        assert "secret-123" not in json.dumps(body)

    def test_shipment_not_found_error_returns_404(self) -> None:
        middleware = _make_middleware()
        request = HttpRequest()
        exc = ShipmentNotFoundError("abc-123")

        response = middleware.process_exception(request, exc)

        assert response is not None
        assert response.status_code == 404
        body = _parse_json(response)
        assert body["code"] == "shipment_not_found"
        assert "abc-123" in body["detail"]

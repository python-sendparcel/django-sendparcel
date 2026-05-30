"""Django middleware for sendparcel exception handling.

Supports both WSGI (sync) and ASGI (async) request/response cycles.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    ProviderCapabilityError,
    ProviderNotFoundError,
    SendParcelException,
    ShipmentNotFoundError,
)

_EXCEPTION_MAP: list[tuple[type[SendParcelException], int, str]] = [
    (ShipmentNotFoundError, 404, "shipment_not_found"),
    (ProviderNotFoundError, 404, "provider_not_found"),
    (ProviderCapabilityError, 409, "provider_capability_error"),
    (CommunicationError, 502, "communication_error"),
    (InvalidCallbackError, 400, "invalid_callback"),
    (InvalidTransitionError, 409, "invalid_transition"),
    (SendParcelException, 400, "sendparcel_error"),
]


def _exception_to_response(
    exception: Exception,
) -> HttpResponse | None:
    """Convert a sendparcel exception to an HTTP response."""
    for exc_type, status_code, code in _EXCEPTION_MAP:
        if isinstance(exception, exc_type):
            return JsonResponse(
                {"detail": str(exception), "code": code},
                status=status_code,
            )
    return None


class SendParcelExceptionMiddleware:
    """Map sendparcel exceptions to appropriate HTTP responses.

    Supports both WSGI (sync) and ASGI (async) request/response cycles.
    More specific exception types are checked first.
    """

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
    ) -> None:
        self.get_response = get_response

    # ── WSGI (sync) ──────────────────────────────────────────────

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        return response

    def process_exception(
        self,
        request: HttpRequest,
        exception: Exception,
    ) -> HttpResponse | None:
        return _exception_to_response(exception)

    # ── ASGI (async) ─────────────────────────────────────────────

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        try:
            response = self.get_response(request)
            # If get_response returns a coroutine (async view), await it
            if hasattr(response, "__await__"):
                response = await response
            return response
        except SendParcelException as exc:
            return _exception_to_response(exc)

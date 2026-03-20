"""Django middleware for sendparcel exception handling."""

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


class SendParcelExceptionMiddleware:
    """Map sendparcel exceptions to appropriate HTTP responses.

    Order matters: more specific exception types are checked first.
    """

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
    ) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_exception(
        self,
        request: HttpRequest,
        exception: Exception,
    ) -> HttpResponse | None:
        for exc_type, status_code, code in _EXCEPTION_MAP:
            if isinstance(exception, exc_type):
                return JsonResponse(
                    {"detail": str(exception), "code": code},
                    status=status_code,
                )
        return None

"""Django middleware for sendparcel exception handling.

Supports both WSGI (sync) and ASGI (async) request/response cycles.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
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
    exception: SendParcelException,
) -> HttpResponse:
    """Convert a sendparcel exception to an HTTP response."""
    for exc_type, status_code, code in _EXCEPTION_MAP:
        if isinstance(exception, exc_type):
            return JsonResponse(
                {"detail": str(exception), "code": code},
                status=status_code,
            )
    return JsonResponse(
        {"detail": str(exception), "code": "sendparcel_error"},
        status=400,
    )


class SendParcelExceptionMiddleware:
    """Map sendparcel exceptions to appropriate HTTP responses.

    More specific exception types are checked first. Exceptions that
    are not :class:`SendParcelException` fall through to Django's own
    error handling — they are never converted to JSON here, so
    internal exception text is not leaked to clients.
    """

    sync_capable = True
    async_capable = True

    def __init__(
        self,
        get_response: (
            Callable[[HttpRequest], HttpResponse]
            | Callable[[HttpRequest], Awaitable[HttpResponse]]
        ),
    ) -> None:
        self.get_response = get_response
        self._is_async = iscoroutinefunction(get_response)
        if self._is_async:
            markcoroutinefunction(self)

    def __call__(
        self, request: HttpRequest
    ) -> HttpResponse | Awaitable[HttpResponse]:
        if self._is_async:
            return self.__acall__(request)
        return self.get_response(request)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        try:
            response = self.get_response(request)
            if asyncio.iscoroutine(response):
                return cast("HttpResponse", await response)
            return cast("HttpResponse", response)
        except SendParcelException as exc:
            return _exception_to_response(exc)

    def process_exception(
        self,
        request: HttpRequest,
        exception: Exception,
    ) -> HttpResponse | None:
        if isinstance(exception, SendParcelException):
            return _exception_to_response(exception)
        return None

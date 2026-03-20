"""Protocol adapters for Django domain objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "CallbackRetryStore",
    "DjangoShipmentAdapter",
]


@dataclass
class DjangoShipmentAdapter:
    """Adapter exposing core shipment protocol from a Django model instance."""

    wrapped: Any

    @property
    def pk(self) -> Any:
        return self.wrapped.pk

    @property
    def id(self) -> str:
        return str(self.wrapped.id)

    @id.setter
    def id(self, value: str) -> None:
        self.wrapped.id = value

    @property
    def status(self) -> str:
        return str(self.wrapped.status)

    @status.setter
    def status(self, value: str) -> None:
        self.wrapped.status = value

    @property
    def provider(self) -> str:
        return str(self.wrapped.provider)

    @provider.setter
    def provider(self, value: str) -> None:
        self.wrapped.provider = value

    @property
    def external_id(self) -> str:
        return str(self.wrapped.external_id)

    @external_id.setter
    def external_id(self, value: str) -> None:
        self.wrapped.external_id = value

    @property
    def tracking_number(self) -> str:
        return str(self.wrapped.tracking_number)

    @tracking_number.setter
    def tracking_number(self, value: str) -> None:
        self.wrapped.tracking_number = value

    def save(self, *args: Any, **kwargs: Any) -> Any:
        return self.wrapped.save(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.wrapped, name)


@runtime_checkable
class CallbackRetryStore(Protocol):
    """Storage abstraction for the webhook retry queue.

    Full lifecycle: store -> get_due ->
    mark_succeeded / mark_failed / mark_exhausted.

    Note: Django implementation is sync (not async) due to framework
    constraints.
    """

    def store_failed_callback(
        self,
        shipment_id: str,
        provider_slug: str,
        payload: dict[str, Any],
        headers: dict[str, Any],
    ) -> str:
        """Store a failed callback for later retry. Returns retry ID."""
        ...

    def get_due_retries(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get retries that are due for processing."""
        ...

    def mark_succeeded(self, retry_id: str) -> None:
        """Mark a retry as successfully processed."""
        ...

    def mark_failed(self, retry_id: str, error: str) -> None:
        """Mark a retry as failed and schedule next attempt."""
        ...

    def mark_exhausted(self, retry_id: str) -> None:
        """Mark a retry as exhausted (dead letter)."""
        ...

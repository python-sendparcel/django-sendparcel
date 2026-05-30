"""Tests for background tasks (django-tasks)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from sendparcel.enums import ShipmentStatus
from sendparcel_django.models import CallbackRetry
from sendparcel_django.retry import process_due_retries


class TestTaskImports:
    """Tests for task module imports."""

    def test_tasks_module_imports(self) -> None:
        """The module should import successfully."""
        import sendparcel_django.celery as celery_module

        assert hasattr(celery_module, "process_due_retries_task")
        assert hasattr(celery_module, "cleanup_dedup_task")
        assert hasattr(celery_module, "poll_shipment_status_task")
        assert hasattr(celery_module, "poll_all_pending_statuses_task")
        assert hasattr(celery_module, "_poll_single_shipment_status")

    def test_poll_async_available(self) -> None:
        """_poll_single_shipment_status is always available."""
        import sendparcel_django.celery as celery_module

        assert hasattr(celery_module, "_poll_single_shipment_status")
        assert callable(celery_module._poll_single_shipment_status)


class TestPollShipmentStatusAsync:
    """Tests for the async polling function."""

    @pytest.mark.django_db
    async def test_polls_shipment_and_returns_result(self) -> None:
        """Polling a valid shipment returns the provider's status result."""
        # Clean up any existing pending retries from other tests
        await sync_to_async(
            CallbackRetry.objects.filter(status="pending").delete,
        )()

        mock_provider = AsyncMock()
        mock_provider.fetch_shipment_status = AsyncMock(
            return_value={"status": "in_transit"}
        )

        mock_repo = MagicMock()
        mock_shipment = MagicMock()
        mock_shipment.id = "ship-1"
        mock_shipment.provider = "test-provider"
        mock_repo.get_by_id = AsyncMock(return_value=mock_shipment)

        mock_registry = MagicMock()
        mock_registry.get = MagicMock(return_value=mock_provider)

        with (
            patch(
                "sendparcel_django.celery.registry", mock_registry
            ),
            patch(
                "sendparcel_django.celery.ShipmentFlow",
                return_value=AsyncMock(),
            ),
            patch(
                "sendparcel_django.celery.DjangoShipmentRepository",
                return_value=mock_repo,
            ),
        ):
            from sendparcel_django.celery import (
                _poll_single_shipment_status,
            )

            result = await _poll_single_shipment_status(
                "ship-1", "test-provider", max_retries=1, poll_interval=10,
            )

        assert result == {"status": "in_transit"}
        mock_provider.fetch_shipment_status.assert_awaited_once_with(
            mock_shipment
        )

    @pytest.mark.django_db
    async def test_poll_returns_none_when_shipment_not_found(self) -> None:
        """Polling a non-existent shipment returns None."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch(
                "sendparcel_django.celery.ShipmentFlow",
                return_value=AsyncMock(),
            ),
            patch(
                "sendparcel_django.celery.DjangoShipmentRepository",
                return_value=mock_repo,
            ),
        ):
            from sendparcel_django.celery import (
                _poll_single_shipment_status,
            )

            result = await _poll_single_shipment_status(
                "ship-missing", "test-provider", max_retries=1, poll_interval=10,
            )

        assert result is None

    @pytest.mark.django_db
    async def test_poll_retries_on_failure(self) -> None:
        """Polling retries on transient failure and returns result on success."""
        mock_provider = AsyncMock()
        mock_provider.fetch_shipment_status = AsyncMock(
            side_effect=[
                Exception("temp fail"),
                {"status": "delivered"},
            ]
        )

        mock_repo = MagicMock()
        mock_shipment = MagicMock()
        mock_shipment.id = "ship-1"
        mock_repo.get_by_id = AsyncMock(return_value=mock_shipment)

        mock_registry = MagicMock()
        mock_registry.get = MagicMock(return_value=mock_provider)

        with (
            patch(
                "sendparcel_django.celery.registry", mock_registry
            ),
            patch(
                "sendparcel_django.celery.ShipmentFlow",
                return_value=AsyncMock(),
            ),
            patch(
                "sendparcel_django.celery.DjangoShipmentRepository",
                return_value=mock_repo,
            ),
        ):
            from sendparcel_django.celery import (
                _poll_single_shipment_status,
            )

            result = await _poll_single_shipment_status(
                "ship-1",
                "test-provider",
                max_retries=3,
                poll_interval=1,
            )

        assert result == {"status": "delivered"}
        assert mock_provider.fetch_shipment_status.call_count == 2

    @pytest.mark.django_db
    async def test_poll_returns_none_after_max_retries(self) -> None:
        """Polling returns None after exhausting all retries."""
        mock_provider = AsyncMock()
        mock_provider.fetch_shipment_status = AsyncMock(
            side_effect=Exception("persistent fail")
        )

        mock_repo = MagicMock()
        mock_shipment = MagicMock()
        mock_shipment.id = "ship-1"
        mock_repo.get_by_id = AsyncMock(return_value=mock_shipment)

        mock_registry = MagicMock()
        mock_registry.get = MagicMock(return_value=mock_provider)

        with (
            patch(
                "sendparcel_django.celery.registry", mock_registry
            ),
            patch(
                "sendparcel_django.celery.ShipmentFlow",
                return_value=AsyncMock(),
            ),
            patch(
                "sendparcel_django.celery.DjangoShipmentRepository",
                return_value=mock_repo,
            ),
        ):
            from sendparcel_django.celery import (
                _poll_single_shipment_status,
            )

            result = await _poll_single_shipment_status(
                "ship-1",
                "test-provider",
                max_retries=2,
                poll_interval=1,
            )

        assert result is None
        assert mock_provider.fetch_shipment_status.call_count == 2

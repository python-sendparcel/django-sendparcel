"""Tests for background tasks (django-tasks)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTaskImports:
    """Tests for task module imports."""

    def test_tasks_module_imports(self) -> None:
        """The module should import successfully."""
        import sendparcel_django.tasks as tasks_module

        assert hasattr(tasks_module, "process_due_retries_task")
        assert hasattr(tasks_module, "cleanup_dedup_task")
        assert hasattr(tasks_module, "poll_shipment_status_task")
        assert hasattr(tasks_module, "poll_all_pending_statuses_task")
        assert hasattr(tasks_module, "_poll_single_shipment_status")

    def test_poll_async_available(self) -> None:
        """_poll_single_shipment_status is always available."""
        import sendparcel_django.tasks as tasks_module

        assert hasattr(tasks_module, "_poll_single_shipment_status")
        assert callable(tasks_module._poll_single_shipment_status)


class TestPollShipmentStatusAsync:
    """Tests for the async polling function."""

    @pytest.mark.django_db
    async def test_polls_shipment_and_returns_result(self) -> None:
        """Polling a valid shipment returns the flow's status update."""
        mock_repo = MagicMock()
        mock_shipment = MagicMock()
        mock_shipment.id = "ship-1"
        mock_repo.get_by_id = AsyncMock(return_value=mock_shipment)

        mock_flow = AsyncMock()
        mock_outcome = MagicMock()
        mock_outcome.update = {"status": "in_transit"}
        mock_flow.fetch_and_update_status = AsyncMock(
            return_value=mock_outcome,
        )

        with (
            patch(
                "sendparcel_django.tasks.ShipmentFlow",
                return_value=mock_flow,
            ),
            patch(
                "sendparcel_django.tasks.DjangoShipmentRepository",
                return_value=mock_repo,
            ),
        ):
            from sendparcel_django.tasks import (
                _poll_single_shipment_status,
            )

            result = await _poll_single_shipment_status(
                "ship-1",
                "test-provider",
                max_retries=1,
                poll_interval=10,
            )

        assert result == {"status": "in_transit"}
        mock_flow.fetch_and_update_status.assert_awaited_once_with(
            mock_shipment,
        )

    @pytest.mark.django_db
    async def test_poll_returns_none_when_shipment_not_found(self) -> None:
        """Polling a non-existent shipment returns None."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch(
                "sendparcel_django.tasks.ShipmentFlow",
                return_value=AsyncMock(),
            ),
            patch(
                "sendparcel_django.tasks.DjangoShipmentRepository",
                return_value=mock_repo,
            ),
        ):
            from sendparcel_django.tasks import (
                _poll_single_shipment_status,
            )

            result = await _poll_single_shipment_status(
                "ship-missing",
                "test-provider",
                max_retries=1,
                poll_interval=10,
            )

        assert result is None

    @pytest.mark.django_db
    async def test_poll_retries_on_failure(self) -> None:
        """Polling retries on transient failure, returns result on
        success."""
        mock_repo = MagicMock()
        mock_shipment = MagicMock()
        mock_shipment.id = "ship-1"
        mock_repo.get_by_id = AsyncMock(return_value=mock_shipment)

        mock_flow = AsyncMock()
        mock_outcome_ok = MagicMock()
        mock_outcome_ok.update = {"status": "delivered"}
        mock_flow.fetch_and_update_status = AsyncMock(
            side_effect=[
                Exception("temp fail"),
                mock_outcome_ok,
            ],
        )

        with (
            patch(
                "sendparcel_django.tasks.ShipmentFlow",
                return_value=mock_flow,
            ),
            patch(
                "sendparcel_django.tasks.DjangoShipmentRepository",
                return_value=mock_repo,
            ),
        ):
            from sendparcel_django.tasks import (
                _poll_single_shipment_status,
            )

            result = await _poll_single_shipment_status(
                "ship-1",
                "test-provider",
                max_retries=3,
                poll_interval=1,
            )

        assert result == {"status": "delivered"}
        assert mock_flow.fetch_and_update_status.call_count == 2

    @pytest.mark.django_db
    async def test_poll_returns_none_after_max_retries(self) -> None:
        """Polling returns None after exhausting all retries."""
        mock_repo = MagicMock()
        mock_shipment = MagicMock()
        mock_shipment.id = "ship-1"
        mock_repo.get_by_id = AsyncMock(return_value=mock_shipment)

        mock_flow = AsyncMock()
        mock_flow.fetch_and_update_status = AsyncMock(
            side_effect=Exception("persistent fail"),
        )

        with (
            patch(
                "sendparcel_django.tasks.ShipmentFlow",
                return_value=mock_flow,
            ),
            patch(
                "sendparcel_django.tasks.DjangoShipmentRepository",
                return_value=mock_repo,
            ),
        ):
            from sendparcel_django.tasks import (
                _poll_single_shipment_status,
            )

            result = await _poll_single_shipment_status(
                "ship-1",
                "test-provider",
                max_retries=2,
                poll_interval=1,
            )

        assert result is None
        assert mock_flow.fetch_and_update_status.call_count == 2

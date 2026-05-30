"""Tests for management commands."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from asgiref.sync import sync_to_async
from django.core.management import call_command

from sendparcel_django.dedup import DjangoWebhookDedupStore
from sendparcel_django.models import CallbackRetry, WebhookDedup
from sendparcel_django.retry import DjangoCallbackRetryStore, process_due_retries


class TestProcessRetries:
    @pytest.mark.django_db(transaction=True)
    async def test_processes_due_retries(self) -> None:
        """process_due_retries processes pending retries."""
        # Clean up any existing pending retries from other tests
        await sync_to_async(
            CallbackRetry.objects.filter(status="pending").delete,
        )()

        retry_store = DjangoCallbackRetryStore()
        flow = MagicMock()
        flow.handle_callback = AsyncMock()
        repository = MagicMock()
        repository.get_by_id = AsyncMock()

        # Create a pending retry record
        retry_id = await retry_store.store_failed_callback(
            shipment_id="ship-1",
            provider_slug="inpost_courier",
            payload={"event": "picked_up"},
            headers={},
        )
        await sync_to_async(
            CallbackRetry.objects.filter(id=retry_id).update,
        )(
            next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )

        result = await process_due_retries(
            retry_store=retry_store,
            flow=flow,
            repository=repository,
            limit=10,
        )

        assert result == 1
        record = await sync_to_async(CallbackRetry.objects.get)(id=retry_id)
        assert record.status == "succeeded"
        flow.handle_callback.assert_awaited_once()

    @pytest.mark.django_db(transaction=True)
    async def test_marks_exhausted_on_max_attempts(self) -> None:
        """Retries at max attempts are marked exhausted."""
        await sync_to_async(
            CallbackRetry.objects.filter(status="pending").delete,
        )()

        retry_store = DjangoCallbackRetryStore()
        flow = MagicMock()
        flow.handle_callback = AsyncMock(side_effect=Exception("fail"))
        repository = MagicMock()

        # Create a retry at max attempts
        retry_id = await retry_store.store_failed_callback(
            shipment_id="ship-2",
            provider_slug="inpost_courier",
            payload={"event": "picked_up"},
            headers={},
        )
        await sync_to_async(
            CallbackRetry.objects.filter(id=retry_id).update,
        )(
            attempts=5,
            next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )

        result = await process_due_retries(
            retry_store=retry_store,
            flow=flow,
            repository=repository,
            limit=10,
            max_attempts=5,
        )

        assert result == 0
        record = await sync_to_async(CallbackRetry.objects.get)(id=retry_id)
        assert record.status == "exhausted"

    @pytest.mark.django_db(transaction=True)
    async def test_no_due_retries(self) -> None:
        """Returns 0 when no retries are due."""
        await sync_to_async(
            CallbackRetry.objects.filter(status="pending").delete,
        )()

        retry_store = DjangoCallbackRetryStore()
        flow = MagicMock()
        repository = MagicMock()

        result = await process_due_retries(
            retry_store=retry_store,
            flow=flow,
            repository=repository,
            limit=10,
        )

        assert result == 0


class TestCleanupDedup:
    @pytest.mark.django_db
    def test_management_command_runs(self) -> None:
        """Management command runs without error."""
        call_command("cleanup_dedup", "--window", "60")

    @pytest.mark.django_db
    def test_management_command_with_custom_window(self) -> None:
        """Management command accepts custom window parameter."""
        call_command("cleanup_dedup", "--window", "300")

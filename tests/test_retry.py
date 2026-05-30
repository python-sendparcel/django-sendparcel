"""Callback retry mechanism tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from asgiref.sync import sync_to_async
from sendparcel.enums import ShipmentStatus
from sendparcel_django.models import CallbackRetry
from sendparcel_django.retry import (
    DjangoCallbackRetryStore,
    compute_next_retry_at,
    process_due_retries,
)


class TestComputeNextRetryAt:
    def test_first_attempt_uses_base_backoff(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=1, backoff_seconds=60)
        after = datetime.now(tz=UTC)

        assert (
            before + timedelta(seconds=60)
            <= result
            <= after + timedelta(seconds=60)
        )

    def test_second_attempt_doubles_backoff(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=2, backoff_seconds=60)

        expected_min = before + timedelta(seconds=120)
        assert result >= expected_min

    def test_third_attempt_quadruples_backoff(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=3, backoff_seconds=60)

        expected_min = before + timedelta(seconds=240)
        assert result >= expected_min

    def test_backoff_with_different_base(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=1, backoff_seconds=30)

        expected_min = before + timedelta(seconds=30)
        assert result >= expected_min


@pytest.mark.django_db
class TestDjangoCallbackRetryStore:
    async def test_store_failed_callback_creates_record(self) -> None:
        store = DjangoCallbackRetryStore()

        retry_id = await store.store_failed_callback(
            shipment_id="ship-1",
            provider_slug="test-provider",
            payload={"event": "picked_up"},
            headers={"x-token": "abc"},
        )

        assert retry_id is not None
        record = await sync_to_async(CallbackRetry.objects.get)(id=retry_id)
        assert record.shipment_id == "ship-1"
        assert record.payload == {"event": "picked_up"}
        assert record.headers == {"x-token": "abc"}
        assert record.status == "pending"
        assert record.attempts == 0

    async def test_get_due_retries_returns_due_items_only(self) -> None:
        store = DjangoCallbackRetryStore()
        # Due retry
        await store.store_failed_callback("ship-due", "test-provider", {}, {})
        await sync_to_async(
            CallbackRetry.objects.filter(shipment_id="ship-due").update,
        )(
            next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )
        # Future retry
        await store.store_failed_callback("ship-future", "test-provider", {}, {})
        await sync_to_async(
            CallbackRetry.objects.filter(shipment_id="ship-future").update,
        )(
            next_retry_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )

        due = await store.get_due_retries(limit=10)

        shipment_ids = [r["shipment_id"] for r in due]
        assert "ship-due" in shipment_ids
        assert "ship-future" not in shipment_ids

    async def test_get_due_retries_respects_limit(self) -> None:
        store = DjangoCallbackRetryStore()
        for i in range(5):
            await store.store_failed_callback(f"ship-{i}", "test-provider", {}, {})
        await sync_to_async(
            CallbackRetry.objects.update,
        )(
            next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )

        due = await store.get_due_retries(limit=3)

        assert len(due) == 3

    async def test_mark_succeeded_changes_status(self) -> None:
        store = DjangoCallbackRetryStore()
        retry_id = await store.store_failed_callback(
            "ship-1", "test-provider", {}, {}
        )

        await store.mark_succeeded(retry_id)

        record = await sync_to_async(CallbackRetry.objects.get)(id=retry_id)
        assert record.status == "succeeded"

    async def test_mark_failed_increments_attempts(self) -> None:
        store = DjangoCallbackRetryStore()
        retry_id = await store.store_failed_callback(
            "ship-1", "test-provider", {}, {}
        )

        await store.mark_failed(retry_id, error="Connection refused")

        record = await sync_to_async(CallbackRetry.objects.get)(id=retry_id)
        assert record.attempts == 1
        assert record.last_error == "Connection refused"
        assert record.next_retry_at is not None
        assert record.next_retry_at > datetime.now(tz=UTC)

    async def test_mark_exhausted_changes_status(self) -> None:
        store = DjangoCallbackRetryStore()
        retry_id = await store.store_failed_callback(
            "ship-1", "test-provider", {}, {}
        )

        await store.mark_exhausted(retry_id)

        record = await sync_to_async(CallbackRetry.objects.get)(id=retry_id)
        assert record.status == "exhausted"

    async def test_pending_retries_with_null_next_retry_at_are_due(self) -> None:
        """Records with no next_retry_at (just created) should be returned."""
        store = DjangoCallbackRetryStore()
        await store.store_failed_callback("ship-null", "test-provider", {}, {})

        due = await store.get_due_retries(limit=10)

        shipment_ids = [r["shipment_id"] for r in due]
        assert "ship-null" in shipment_ids


@pytest.mark.django_db
class TestProcessDueRetries:
    async def test_processes_due_retries_calls_flow(self) -> None:
        # Clean up any existing pending retries from other tests
        await sync_to_async(
            CallbackRetry.objects.filter(status="pending").delete,
        )()

        store = DjangoCallbackRetryStore()
        retry_id = await store.store_failed_callback(
            "ship-retry",
            "test-provider",
            {"event": "delivered"},
            {"x-token": "ok"},
        )
        await sync_to_async(
            CallbackRetry.objects.filter(id=retry_id).update,
        )(
            next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )

        mock_flow = AsyncMock()
        mock_repo = AsyncMock()
        mock_shipment = AsyncMock()
        mock_shipment.id = "ship-retry"
        mock_shipment.status = ShipmentStatus.IN_TRANSIT
        mock_repo.get_by_id.return_value = mock_shipment
        mock_flow.handle_callback.return_value = mock_shipment

        processed = await process_due_retries(
            retry_store=store,
            flow=mock_flow,
            repository=mock_repo,
            max_attempts=5,
        )

        assert processed == 1
        record = await sync_to_async(CallbackRetry.objects.get)(
            shipment_id="ship-retry"
        )
        assert record.status == "succeeded"

    async def test_marks_exhausted_after_max_attempts(self) -> None:
        store = DjangoCallbackRetryStore()
        retry_id = await store.store_failed_callback(
            "ship-exhaust", "test-provider", {}, {}
        )
        await sync_to_async(
            CallbackRetry.objects.filter(id=retry_id).update,
        )(
            attempts=4,
            next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )

        mock_flow = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.side_effect = Exception("not found")

        processed = await process_due_retries(
            retry_store=store,
            flow=mock_flow,
            repository=mock_repo,
            max_attempts=5,
        )

        assert processed == 0
        record = await sync_to_async(CallbackRetry.objects.get)(id=retry_id)
        assert record.status == "exhausted"

    async def test_marks_failed_on_error_within_attempts(self) -> None:
        store = DjangoCallbackRetryStore()
        retry_id = await store.store_failed_callback(
            "ship-fail", "test-provider", {}, {}
        )
        await sync_to_async(
            CallbackRetry.objects.filter(id=retry_id).update,
        )(
            attempts=1,
            next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )

        mock_flow = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.side_effect = Exception("temporary error")

        processed = await process_due_retries(
            retry_store=store,
            flow=mock_flow,
            repository=mock_repo,
            max_attempts=5,
        )

        assert processed == 0
        record = await sync_to_async(CallbackRetry.objects.get)(id=retry_id)
        assert record.status == "pending"
        assert record.attempts == 2
        assert record.last_error is not None
        assert "temporary error" in record.last_error

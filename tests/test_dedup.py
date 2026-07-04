"""Tests for the webhook dedup store."""

from __future__ import annotations

import pytest
from asgiref.sync import sync_to_async
from django.db import IntegrityError
from sendparcel.types import CallbackContext
from sendparcel_django.dedup import DjangoWebhookDedupStore
from sendparcel_django.models import WebhookDedup


def _ctx(
    payload: dict | None = None,
    *,
    shipment_id: str = "1",
    source_ip: str = "127.0.0.1",
    headers: dict | None = None,
    raw_body: bytes | None = None,
) -> CallbackContext:
    """Build a CallbackContext with defaults for dedup tests."""
    payload = payload or {"status": "created"}
    return CallbackContext(
        shipment_id=shipment_id,
        payload=payload,
        headers=headers or {},
        source_ip=source_ip,
        raw_body=raw_body or b"",
    )


class TestCallbackContextDedupHash:
    def test_deterministic_across_insertion_order(self) -> None:
        """Identical payloads hash the same regardless of key order."""
        a = _ctx(payload={"b": 2, "a": 1})
        b = _ctx(payload={"a": 1, "b": 2})
        assert a.dedup_hash == b.dedup_hash

    def test_empty_payload(self) -> None:
        ctx = _ctx(payload={})
        assert ctx.dedup_hash != ""
        assert len(ctx.dedup_hash) == 64  # SHA-256 hex digest

    def test_nested_dict(self) -> None:
        a = _ctx(payload={"outer": {"z": 1, "a": 2}})
        b = _ctx(payload={"outer": {"a": 2, "z": 1}})
        assert a.dedup_hash == b.dedup_hash

    def test_different_payloads_different_hashes(self) -> None:
        a = _ctx(payload={"status": "created"})
        b = _ctx(payload={"status": "delivered"})
        assert a.dedup_hash != b.dedup_hash

    def test_headers_do_not_affect_hash(self) -> None:
        """Headers and source_ip must not affect the dedup hash."""
        a = _ctx(payload={"status": "created"}, headers={"X-Token": "abc"})
        b = _ctx(payload={"status": "created"}, headers={"X-Token": "xyz"})
        assert a.dedup_hash == b.dedup_hash


class TestDjangoWebhookDedupStore:
    @pytest.mark.django_db(transaction=True)
    async def test_is_duplicate_returns_false_on_first_call(self) -> None:
        """First call with a new payload should return False."""
        store = DjangoWebhookDedupStore()
        ctx = _ctx()
        assert await store.is_duplicate(ctx) is False

    @pytest.mark.django_db(transaction=True)
    async def test_is_duplicate_returns_true_on_second_call(self) -> None:
        """Second call with the same payload should return True."""
        store = DjangoWebhookDedupStore()
        ctx = _ctx()
        assert await store.is_duplicate(ctx) is False
        assert await store.is_duplicate(ctx) is True

    @pytest.mark.django_db(transaction=True)
    async def test_different_payloads_not_deduped(self) -> None:
        """Different payloads should not be considered duplicates."""
        store = DjangoWebhookDedupStore()
        a = _ctx(payload={"status": "created"})
        b = _ctx(payload={"status": "delivered"})
        assert await store.is_duplicate(a) is False
        assert await store.is_duplicate(b) is False

    @pytest.mark.django_db(transaction=True)
    async def test_different_shipments_not_deduped(self) -> None:
        """Same payload for different shipments should not be deduped."""
        store = DjangoWebhookDedupStore()
        a = _ctx(shipment_id="1")
        b = _ctx(shipment_id="2")
        assert await store.is_duplicate(a) is False
        assert await store.is_duplicate(b) is False

    @pytest.mark.django_db(transaction=True)
    async def test_cleanup_removes_old_entries(self) -> None:
        """cleanup_old_entries should remove records older than the window."""
        store = DjangoWebhookDedupStore(window_seconds=0)
        ctx = _ctx()
        await store.is_duplicate(ctx)
        # With window_seconds=0, all entries are immediately stale
        deleted = await store.cleanup_old_entries()
        assert deleted >= 1

    @pytest.mark.django_db(transaction=True)
    async def test_cleanup_does_nothing_when_empty(self) -> None:
        store = DjangoWebhookDedupStore()
        deleted = await store.cleanup_old_entries()
        assert deleted == 0

    @pytest.mark.django_db(transaction=True)
    async def test_window_parameter_respected(self) -> None:
        """A payload just inserted should not be considered duplicate
        until the window expires — but since we use IntegrityError for
        dedup detection, the window only affects cleanup."""
        store = DjangoWebhookDedupStore(window_seconds=900)
        ctx = _ctx()
        assert await store.is_duplicate(ctx) is False
        assert await store.is_duplicate(ctx) is True

    @pytest.mark.django_db(transaction=True)
    async def test_is_duplicate_handles_integrity_error(self) -> None:
        """IntegrityError from concurrent inserts should return True."""
        store = DjangoWebhookDedupStore()
        ctx = _ctx()
        # First call inserts
        assert await store.is_duplicate(ctx) is False
        # Second call triggers IntegrityError → returns True
        assert await store.is_duplicate(ctx) is True

    @pytest.mark.django_db(transaction=True)
    async def test_provider_slug_stored(self) -> None:
        """The provider_slug should be persisted."""
        store = DjangoWebhookDedupStore()
        ctx = _ctx()
        await store.is_duplicate(ctx, provider_slug="inpost_locker")
        record = await sync_to_async(WebhookDedup.objects.get)(shipment_id="1")
        assert record.provider_slug == "inpost_locker"

    @pytest.mark.django_db(transaction=True)
    async def test_unique_constraint_on_shipment_hash(self) -> None:
        """Direct DB insert with same (shipment_id, payload_hash)
        should fail."""
        store = DjangoWebhookDedupStore()
        ctx = _ctx()
        await store.is_duplicate(ctx)
        # Try to insert the same combination directly
        with pytest.raises(IntegrityError):
            await sync_to_async(WebhookDedup.objects.create)(
                payload_hash=ctx.dedup_hash,
                shipment_id="1",
                provider_slug="test",
            )

"""Tests for the webhook dedup store."""

from __future__ import annotations

import pytest
from asgiref.sync import sync_to_async
from django.db import IntegrityError
from sendparcel_django.dedup import (
    DjangoWebhookDedupStore,
    compute_payload_hash,
)
from sendparcel_django.models import WebhookDedup


class TestComputePayloadHash:
    def test_deterministic_across_insertion_order(self) -> None:
        """Identical keys must produce the same hash regardless of order."""
        a = {"b": 2, "a": 1}
        b = {"a": 1, "b": 2}
        assert compute_payload_hash(a) == compute_payload_hash(b)

    def test_empty_dict(self) -> None:
        assert compute_payload_hash({}) != ""

    def test_nested_dict(self) -> None:
        a = {"outer": {"z": 1, "a": 2}}
        b = {"outer": {"a": 2, "z": 1}}
        assert compute_payload_hash(a) == compute_payload_hash(b)

    def test_different_payloads_different_hashes(self) -> None:
        a = {"status": "created"}
        b = {"status": "delivered"}
        assert compute_payload_hash(a) != compute_payload_hash(b)

    def test_handles_non_string_values(self) -> None:
        """Non-string values should be converted via str()."""
        payload = {"count": 42, "flag": True}
        h = compute_payload_hash(payload)
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest


class TestDjangoWebhookDedupStore:
    @pytest.mark.django_db(transaction=True)
    async def test_is_duplicate_returns_false_on_first_call(self) -> None:
        """First call with a new payload should return False."""
        store = DjangoWebhookDedupStore()
        payload = {"status": "created"}
        assert await store.is_duplicate(payload, "1") is False

    @pytest.mark.django_db(transaction=True)
    async def test_is_duplicate_returns_true_on_second_call(self) -> None:
        """Second call with the same payload should return True."""
        store = DjangoWebhookDedupStore()
        payload = {"status": "created"}
        assert await store.is_duplicate(payload, "1") is False
        assert await store.is_duplicate(payload, "1") is True

    @pytest.mark.django_db(transaction=True)
    async def test_different_payloads_not_deduped(self) -> None:
        """Different payloads should not be considered duplicates."""
        store = DjangoWebhookDedupStore()
        a = {"status": "created"}
        b = {"status": "delivered"}
        assert await store.is_duplicate(a, "1") is False
        assert await store.is_duplicate(b, "1") is False

    @pytest.mark.django_db(transaction=True)
    async def test_different_shipments_not_deduped(self) -> None:
        """Same payload for different shipments should not be deduped."""
        store = DjangoWebhookDedupStore()
        payload = {"status": "created"}
        assert await store.is_duplicate(payload, "1") is False
        assert await store.is_duplicate(payload, "2") is False

    @pytest.mark.django_db(transaction=True)
    async def test_cleanup_removes_old_entries(self) -> None:
        """cleanup_old_entries should remove records older than the window."""
        store = DjangoWebhookDedupStore(window_seconds=0)
        payload = {"status": "created"}
        await store.is_duplicate(payload, "1")
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
        payload = {"status": "created"}
        assert await store.is_duplicate(payload, "1") is False
        assert await store.is_duplicate(payload, "1") is True

    @pytest.mark.django_db(transaction=True)
    async def test_is_duplicate_handles_integrity_error(self) -> None:
        """IntegrityError from concurrent inserts should return True."""
        store = DjangoWebhookDedupStore()
        payload = {"status": "created"}
        # First call inserts
        assert await store.is_duplicate(payload, "1") is False
        # Second call triggers IntegrityError → returns True
        assert await store.is_duplicate(payload, "1") is True

    @pytest.mark.django_db(transaction=True)
    async def test_provider_slug_stored(self) -> None:
        """The provider_slug should be persisted."""
        store = DjangoWebhookDedupStore()
        payload = {"status": "created"}
        await store.is_duplicate(payload, "1", provider_slug="inpost_locker")
        record = await sync_to_async(WebhookDedup.objects.get)(shipment_id="1")
        assert record.provider_slug == "inpost_locker"

    @pytest.mark.django_db(transaction=True)
    async def test_unique_constraint_on_shipment_hash(self) -> None:
        """Direct DB insert with same (shipment_id, payload_hash)
        should fail."""
        store = DjangoWebhookDedupStore()
        payload = {"status": "created"}
        await store.is_duplicate(payload, "1")
        # Try to insert the same combination directly
        with pytest.raises(IntegrityError):
            await sync_to_async(WebhookDedup.objects.create)(
                payload_hash=compute_payload_hash(payload),
                shipment_id="1",
                provider_slug="test",
            )

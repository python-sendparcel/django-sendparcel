"""DjangoShipmentRepository tests."""

import pytest
from sendparcel.enums import ShipmentStatus
from sendparcel.exceptions import ShipmentNotFoundError
from sendparcel_django.repository import DjangoShipmentRepository


@pytest.mark.django_db
class TestDjangoShipmentRepository:
    def setup_method(self):
        self.repo = DjangoShipmentRepository()

    @pytest.mark.asyncio
    async def test_create_shipment(self):
        shipment = await self.repo.create(
            reference_id="ref-1",
            provider="dummy",
            status=ShipmentStatus.NEW,
        )

        assert shipment.pk is not None
        assert shipment.reference_id == "ref-1"
        assert shipment.provider == "dummy"
        assert shipment.status == ShipmentStatus.NEW

    @pytest.mark.asyncio
    async def test_get_by_id(self):
        created = await self.repo.create(
            reference_id="ref-2",
            provider="dummy",
            status=ShipmentStatus.NEW,
        )

        fetched = await self.repo.get_by_id(str(created.pk))

        assert fetched.pk == created.pk
        assert fetched.reference_id == "ref-2"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found_raises(self):
        with pytest.raises(ShipmentNotFoundError):
            await self.repo.get_by_id("99999")

    @pytest.mark.asyncio
    async def test_save_persists_changes(self):
        shipment = await self.repo.create(
            reference_id="ref-3",
            provider="dummy",
            status=ShipmentStatus.NEW,
        )
        shipment.tracking_number = "TRACK-123"

        saved = await self.repo.save(shipment)

        fetched = await self.repo.get_by_id(str(saved.pk))
        assert fetched.tracking_number == "TRACK-123"

    @pytest.mark.asyncio
    async def test_update_status(self):
        shipment = await self.repo.create(
            reference_id="ref-4",
            provider="dummy",
            status=ShipmentStatus.NEW,
        )

        updated = await self.repo.update_status(
            str(shipment.pk),
            ShipmentStatus.CREATED,
            external_id="ext-99",
        )

        assert updated.status == ShipmentStatus.CREATED
        assert updated.external_id == "ext-99"

        # Verify persisted to DB
        fetched = await self.repo.get_by_id(str(shipment.pk))
        assert fetched.status == ShipmentStatus.CREATED
        assert fetched.external_id == "ext-99"

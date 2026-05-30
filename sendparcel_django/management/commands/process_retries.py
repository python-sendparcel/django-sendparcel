"""Management command to process pending callback retries."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from sendparcel_django.retry import DjangoCallbackRetryStore, process_due_retries

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Process pending callback retry records."""

    help = "Process pending webhook callback retries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Maximum number of retries to process (default: 10)",
        )
        parser.add_argument(
            "--max-attempts",
            type=int,
            default=5,
            help="Maximum retry attempts before marking as exhausted (default: 5)",
        )
        parser.add_argument(
            "--backoff",
            type=int,
            default=60,
            help="Base backoff seconds for exponential retry (default: 60)",
        )

    async def handle_async(self, *args, **options):
        retry_store = DjangoCallbackRetryStore()
        # Import flow and repository from the app registry
        from sendparcel.flow import ShipmentFlow
        from sendparcel_django.repository import DjangoShipmentRepository

        flow = ShipmentFlow()
        repository = DjangoShipmentRepository()

        count = await process_due_retries(
            retry_store=retry_store,
            flow=flow,
            repository=repository,
            max_attempts=options["max_attempts"],
            backoff_seconds=options["backoff"],
            limit=options["limit"],
        )

        self.stdout.write(
            self.style.SUCCESS(f"Processed {count} retry record(s).")
        )

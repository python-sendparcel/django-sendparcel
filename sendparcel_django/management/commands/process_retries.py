"""Management command to process pending callback retries."""

from __future__ import annotations

import asyncio
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from sendparcel.logging import get_logger

from sendparcel_django.retry import (
    DjangoCallbackRetryStore,
    process_due_retries,
)

logger = get_logger(__name__)


class Command(BaseCommand):
    """Process pending callback retry records."""

    help = "Process pending webhook callback retries."

    def add_arguments(self, parser: CommandParser) -> None:
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
            help=(
                "Maximum retry attempts before marking as exhausted "
                "(default: 5)"
            ),
        )
        parser.add_argument(
            "--backoff",
            type=int,
            default=60,
            help="Base backoff seconds for exponential retry (default: 60)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Synchronous entry point — uses asyncio.run() to execute
        the async retry processing logic.

        Django management commands are sync by convention; ``asyncio.run()``
        creates and closes a fresh event loop for each invocation,
        avoiding resource leaks from manual loop management.
        """
        asyncio.run(self._handle_async(*args, **options))

    async def _handle_async(self, *args: Any, **options: Any) -> None:
        retry_store = DjangoCallbackRetryStore()
        from sendparcel.flow import ShipmentFlow

        from sendparcel_django.repository import DjangoShipmentRepository

        repository = DjangoShipmentRepository()
        flow = ShipmentFlow(repository=repository)

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

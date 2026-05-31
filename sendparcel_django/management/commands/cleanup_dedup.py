"""Management command to clean up old webhook dedup records."""

from __future__ import annotations

import asyncio
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from sendparcel_django.dedup import DjangoWebhookDedupStore


class Command(BaseCommand):
    """Remove expired webhook deduplication records."""

    help = "Remove webhook dedup records older than the configured window."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--window",
            type=int,
            default=900,
            help="Age in seconds after which records are considered stale "
            "(default: 900 = 15 minutes)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                self.handle_async(*args, **options)
            )
        finally:
            loop.close()

    async def handle_async(self, *args: Any, **options: Any) -> None:
        store = DjangoWebhookDedupStore(window_seconds=options["window"])
        deleted = await store.cleanup_old_entries()
        self.stdout.write(
            self.style.SUCCESS(f"Cleaned up {deleted} dedup record(s).")
        )

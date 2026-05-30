"""Health check endpoints for django-sendparcel.

Provides health check views for monitoring provider availability
and system status. Useful for Kubernetes liveness/readiness probes,
load balancer health checks, and monitoring dashboards.

Usage::

    from django.urls import path
    from sendparcel_django.health import HealthCheckView

    urlpatterns = [
        path("health/", HealthCheckView.as_view(), name="sendparcel_health"),
    ]

Response format::

    {
        "status": "ok",
        "timestamp": "2024-01-01T00:00:00Z",
        "checks": {
            "database": {"status": "ok"},
            "providers": {
                "inpost-courier": {"status": "ok"},
                "inpost-locker": {"status": "degraded"}
            }
        }
    }
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from django.http import HttpRequest, JsonResponse
from sendparcel.logging import get_logger

logger = get_logger(__name__)


class HealthCheckView:
    """Health check view for sendparcel.

    Checks database connectivity and provider availability.
    Returns 200 OK if all checks pass, 503 Service Unavailable
    if any critical check fails.
    """

    def __init__(self, providers: list[str] | None = None) -> None:
        """
        Args:
            providers: List of provider slugs to check.
                If None, checks all registered providers.
        """
        self.providers = providers

    def __call__(self, request: HttpRequest) -> JsonResponse:
        """Handle health check request."""
        checks = self._run_checks()
        all_ok = True
        for key, check in checks.items():
            if isinstance(check, dict):
                if key == "providers":
                    # Empty providers dict is ok (no providers configured)
                    if not check:
                        continue
                    # Check nested providers
                    for provider_status in check.values():
                        if isinstance(provider_status, dict):
                            if provider_status.get("status") != "ok":
                                all_ok = False
                                break
                elif check.get("status") != "ok":
                    all_ok = False
                    break
            else:
                all_ok = False
                break

        status_code = 200 if all_ok else 503
        return JsonResponse(
            {
                "status": "ok" if all_ok else "degraded",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "checks": checks,
            },
            status=status_code,
        )

    def _run_checks(self) -> dict[str, Any]:
        """Run all health checks."""
        checks: dict[str, Any] = {}

        # Database check
        checks["database"] = self._check_database()

        # Provider checks
        checks["providers"] = self._check_providers()

        return checks

    def _check_database(self) -> dict[str, Any]:
        """Check database connectivity."""
        try:
            from django.db import connection

            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return {"status": "ok"}
        except Exception as exc:
            logger.error("Database health check failed: %s", exc)
            return {"status": "error", "detail": str(exc)}

    def _check_providers(self) -> dict[str, Any]:
        """Check provider availability."""
        from sendparcel.registry import registry

        providers: dict[str, Any] = {}
        provider_slugs = self.providers or [
            slug for slug in registry._providers.keys()
        ]

        for slug in provider_slugs:
            try:
                provider_class = registry.get_by_slug(slug)
                # Check if provider has a health check method
                if hasattr(provider_class, "health_check"):
                    result = provider_class.health_check()
                    providers[slug] = {
                        "status": result.get("status", "ok"),
                        "detail": result.get("detail", ""),
                    }
                else:
                    # No health check method — assume ok
                    providers[slug] = {"status": "ok"}
            except Exception as exc:
                logger.warning("Provider health check failed for %s: %s", slug, exc)
                providers[slug] = {"status": "error", "detail": str(exc)}

        return providers


# Module-level view instance for easy import.
health_check = HealthCheckView()

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-07-04

### Fixed

- Callback processing now runs inside a single database transaction
  with the shipment row locked (`select_for_update`) across the
  provider call and the write — concurrent callbacks for one shipment
  are actually serialized, matching what the docs promised. The
  redundant full-row `save()` after the flow's atomic field update
  was removed.
- A failed callback releases its dedup claim, so a provider
  redelivery of the identical payload is processed instead of being
  silently dropped as a duplicate.
- `SendParcelExceptionMiddleware.process_exception` returns `None`
  for exceptions that are not `SendParcelException` — unknown errors
  fall through to Django's own handling instead of leaking
  `str(exception)` to clients as JSON.
- Added the database-level unique constraint on
  `(provider, reference_id)` (blank `reference_id` exempt) that
  `create_with_idempotency_key` documented but never had; the
  concurrent-create race is now actually resolved. Includes migration
  `0008`.
- Health check no longer reaches into the registry's private state
  (uses the new `PluginRegistry.slugs()`) and only invokes
  `health_check` when it is defined as a classmethod.
- Ships the core `flow.create_shipment` order/reference kwarg routing
  fix — closes the order-linkage data-loss bug documented in
  `docs/bug-order-linkage-and-adapter-silent-writes.md`.

### Changed (breaking)

- Requires `python-sendparcel>=0.3.0`.
- `DjangoShipmentAdapter` is gone (removed after 0.2.0): the
  repository returns raw model instances that satisfy the core
  `Shipment` protocol structurally.
- Middleware is now natively async-capable (`async_capable = True`).

## [0.2.0] - 2025-06-05

### Changed

- Adapted to the python-sendparcel 0.2.x API: `CallbackContext`
  callbacks, `CallbackProcessor` extracted from the view, webhook
  dedup store, callback retry persistence.

## [0.1.0] - 2025-02-16

### Added

- Django adapter for python-sendparcel
- Swappable `Shipment` model (like Django's `AUTH_USER_MODEL`)
- `DjangoShipmentAdapter` for bridging Django models to sendparcel protocols
- `DjangoShipmentRepository` with full ORM persistence
- Django views for shipment creation, callback handling, and label serving
- Django app configuration with `SENDPARCEL` settings dict
- Example project with full shipping simulation UI
- Full test suite (124 tests)

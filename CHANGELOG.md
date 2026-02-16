# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2025-02-16

### Added

- Django adapter for python-sendparcel
- Swappable `Shipment` model (like Django's `AUTH_USER_MODEL`)
- `DjangoOrderAdapter` for bridging Django models to sendparcel protocols
- `DjangoShipmentRepository` with full ORM persistence
- Django views for shipment creation, callback handling, and label serving
- Django app configuration with `SENDPARCEL` settings dict
- Example project with full shipping simulation UI
- Full test suite (124 tests)

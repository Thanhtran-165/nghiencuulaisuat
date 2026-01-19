# Changelog

All notable changes to VN Bond Lab will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0-rc1] - 2026-01-13

### Added
- **Phase 9**: Release Candidate with demo mode and smoke runbook
  - Version information API endpoint (`/api/version`)
  - Demo mode with synthetic seed data (`DEMO_MODE=true`)
  - Smoke test runbook for operator verification
  - Upgrade and rollback procedures

- **Phase 8**: Observability + Monitoring + Deployment
  - Health check endpoint (`/healthz`) - quick liveness probe
  - Readiness check endpoint (`/readyz`) - DB and schema verification
  - Prometheus metrics endpoint (`/metrics`)
  - Monitoring dashboard (`/admin/monitoring`)
  - Provider reliability tracking
  - Source drift detection (fingerprinting)
  - Request correlation IDs
  - Structured logging (JSON/text toggle)
  - SLO metrics (30-day success rates)
  - Production Docker Compose configuration
  - Systemd service template
  - GitHub Actions CI pipeline

- **Phase 8.1**: Config Cleanup + Verification
  - Standardized environment variables (`ADMIN_AUTH_*` canonical)
  - Backwards compatibility for `BASIC_AUTH_*` (deprecated)
  - Verification tests for backwards compatibility
  - `/readyz` contract tests
  - `/metrics` contract tests
  - "python command not found" troubleshooting in docs

- **Phase 7**: Data Quality Framework + Operations
  - Data quality rules engine with PASS/WARN/ERROR statuses
  - Admin DQ dashboard (`/admin/quality`)
  - Alert thresholds configuration
  - Backup and restore functionality
  - Optional Basic Authentication for admin endpoints
  - Version manifest

- **Phase 6**: Advanced Analytics
  - Transmission analytics (policy rate transmission to yields)
  - BondY stress model scenario analysis
  - Vietnamese daily snapshot generator

- **Phase 5**: Secondary Trading + Policy Rates
  - Secondary trading data collection (HNX)
  - Policy rates data collection (SBV)
  - Policy rates UI and API

- **Phase 4**: Auction Results + Enhanced UI
  - Auction results data collection (HNX)
  - Enhanced UI with "liquid glass" styling
  - Interactive charts with Chart.js

- **Phase 3**: Interbank Rates + Backfill
  - Interbank rate data collection (SBV)
  - Historical backfill functionality
  - Ingestion pipeline architecture

- **Phase 2**: Yield Curve Data
  - Yield curve data collection (HNX)
  - Database schema (DuckDB)
  - RESTful API endpoints

- **Phase 1**: Project Setup
  - FastAPI application structure
  - Docker containerization
  - Basic UI framework

### Changed
- Updated all documentation to use `ADMIN_AUTH_*` instead of `BASIC_AUTH_*`
- Improved error handling and logging throughout
- Enhanced Docker Compose configurations for production

### Deprecated
- `BASIC_AUTH_ENABLED`, `BASIC_AUTH_USERNAME`, `BASIC_AUTH_PASSWORD` - Use `ADMIN_AUTH_*` instead
- Old environment variables are automatically mapped with deprecation warnings

### Removed
- None

### Fixed
- Fixed issue with provider parsing failures
- Improved database connection handling
- Enhanced secret redaction in logs

### Security
- Admin endpoints now support optional Basic Authentication
- Secrets (passwords, API keys) are automatically redacted from logs
- Metrics endpoint can be protected separately
- Source fingerprinting for drift detection

### Breaking Changes
- **None** - Fully backwards compatible release

---

## [1.0.0] - 2026-01-19

### Added
- `.dockerignore` to keep Docker build context small and avoid copying local state (data/logs/node_modules) into images.

### Changed
- Docker Compose: remove fixed `container_name` to avoid name conflicts on user machines.
- Docker Compose: allow host port override via `HOST_PORT` (default `8000`).
- Docker Compose: healthcheck uses `/healthz`.
- Documentation: clarify local (8001) vs Docker (8000) ports and add a Docker quick start.
- Documentation: call out datasets that are “latest only” and must accumulate day-by-day (see `docs/MEMO_DATA_WAITING_FILL.md`).

### Fixed
- Reduce “clone → build” friction caused by unnecessarily large Docker build contexts.

## [Unreleased]

### Planned
- Additional provider integrations
- Enhanced alert notification channels
- Performance optimizations for large datasets
- Additional analytics features

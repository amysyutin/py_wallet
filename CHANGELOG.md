# Changelog

All notable changes to the **py_wallet** application are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Deployment and platform changes are tracked separately in
[`amysyutin/py_wallet-infra`](https://github.com/amysyutin/py_wallet-infra).

## [Unreleased]

## [0.2.0] - 2026-07-22

### Added

- Telegram Mini App authentication and bot integration.
- Wallet groups, manual wallets and balances, and expanded portfolio APIs.
- Snapshot-service integration, scheduled snapshot jobs, and product metrics.
- Component SemVer validation and immutable release-image promotion.

### Security

- Hardened password handling, configuration validation, dependency auditing,
  and the validated GitOps deployment path.

## [0.1.0] - 2026-06-10

First public version of the crypto portfolio service.

### Added

- FastAPI service with async PostgreSQL persistence and Alembic migrations.
- EVM portfolio aggregation across Ethereum Mainnet, Base, BNB Chain, Arbitrum,
  and Linea (native token, USDT, USDC).
- USD valuation via RPC token balances and CoinGecko native token prices.
- JWT authentication: user registration, login, and `/auth/me`.
- Per-user wallets, balance snapshots, portfolio history, and portfolio summary.
- Split health endpoints: `/health`, `/health/live`, `/health/ready`.
- Prometheus `/metrics` endpoint via instrumentator.
- Docker image and Docker Compose stack for local development.
- CI pipeline: ruff lint, black format check, pytest, Docker Compose smoke test.
- Security CI: Gitleaks (blocking), pip-audit and Bandit (advisory), JWT config
  fail-fast check.
- Main-branch pipeline: immutable GHCR image by commit SHA, GitOps image tag bump
  in the infra repo, and Telegram notifications.

### Security

- JWT secret hardening: environment-aware validation, insecure placeholders
  rejected in staging/production, dev-only implicit secret with a startup warning.

### Known limitations

- Refresh tokens are not implemented; rotating `JWT_SECRET` forces re-login.
- Secrets are managed as out-of-band Kubernetes Secrets (SOPS/SealedSecrets planned).
- Snapshot collection supports EVM wallets only.

See [`docs/SECURITY_BACKLOG.md`](docs/SECURITY_BACKLOG.md) for the full hardening backlog.

[Unreleased]: https://github.com/amysyutin/py_wallet/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/amysyutin/py_wallet/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/amysyutin/py_wallet/releases/tag/v0.1.0

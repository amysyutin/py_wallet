# Changelog

All notable changes to the **py_wallet** application are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Deployment and platform changes are tracked separately in
[`amysyutin/py_wallet-infra`](https://github.com/amysyutin/py_wallet-infra).

## [Unreleased]

## [0.1.0] - 2026-06-10

First public version of the crypto portfolio service.

### Added

- FastAPI service with async PostgreSQL persistence and Alembic migrations.
- EVM portfolio aggregation across Ethereum Mainnet, Base, BNB Chain, Arbitrum,
  and Linea (native token, USDT, USDC).
- Binance Spot and Simple Earn (Flexible/Locked) balance aggregation.
- USD valuation via Binance public prices and CoinGecko native token prices.
- JWT authentication: user registration, login, and `/auth/me`.
- Role model with admin-only `/binance/balance`; `promote-admin` CLI command.
- Per-user wallets, balance snapshots, portfolio history, and portfolio summary.
- Public `/demo/binance/balance` endpoint with fixed mock data (no external calls).
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
- Real Binance account endpoint gated behind the admin role.

### Known limitations

- Refresh tokens are not implemented; rotating `JWT_SECRET` forces re-login.
- Secrets are managed as out-of-band Kubernetes Secrets (SOPS/SealedSecrets planned).
- Snapshot collection supports EVM wallets only.

See [`docs/SECURITY_BACKLOG.md`](docs/SECURITY_BACKLOG.md) for the full hardening backlog.

[Unreleased]: https://github.com/amysyutin/py_wallet/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/amysyutin/py_wallet/releases/tag/v0.1.0

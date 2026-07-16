# py_wallet

FastAPI service for aggregating and monitoring a crypto portfolio.

The app collects balances from EVM networks, calculates USD values, and stores
wallet snapshots in PostgreSQL. Supported EVM networks are Ethereum Mainnet,
Base, BNB Chain, Arbitrum, and Linea.

The application repository contains the service code, database migrations,
tests, Docker image, and CI pipeline. Kubernetes manifests are maintained in the
separate `amysyutin/py_wallet-infra` repository.

## Features

- EVM portfolio aggregation across multiple chains.
- Native token, USDT, and USDC balance tracking.
- USD valuation through RPC token balances and CoinGecko native token prices.
- PostgreSQL persistence with Alembic migrations.
- User registration and JWT authentication.
- Per-user wallets, balance snapshots, portfolio history, and portfolio summary.
- Local development through Docker Compose.
- GitHub Actions checks, Docker image publishing to GHCR, and GitOps image tag updates.

## Project Structure

```text
py_wallet/
├── app/
│   ├── main.py                       # FastAPI entry point
│   ├── config.py                     # EVM and token configuration
│   ├── core/
│   │   ├── config.py                 # Database and JWT settings
│   │   └── security.py               # Password hashing and JWT helpers
│   ├── db/
│   │   ├── models/                   # SQLAlchemy models
│   │   └── session.py                # Async database sessions
│   ├── routers/
│   │   ├── auth.py                   # Registration, login, current user
│   │   ├── wallet_groups.py          # Wallet group CRUD
│   │   ├── wallets.py                # User wallet management
│   │   ├── snapshots.py              # Balance snapshot creation
│   │   └── portfolio.py              # Portfolio history and summary
│   ├── connectors/                   # RPC, ERC-20, and CoinGecko clients
│   ├── services/                     # Portfolio, snapshot, and admin promote logic
│   ├── demo/                         # Public demo payloads (no external API calls)
│   ├── cli/                          # Operational CLI (promote-admin)
│   └── routes.py                     # Health and legacy aggregation endpoints
├── alembic/                          # Database migrations
├── tests/
├── .github/workflows/
│   ├── ci.yml                        # Pull request checks
│   └── main-build.yml                # Main branch build, publish, GitOps update
├── Dockerfile
├── docker-compose.yml                # Local app and PostgreSQL stack
├── docker-compose.ci.yml             # CI smoke-test stack
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── pytest.ini
```

## API

Public endpoints:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Basic availability check. Returns `{"status": "ok"}`. |
| `GET` | `/health` | Database health check. Includes non-sensitive application version and build SHA. |
| `POST` | `/auth/register` | Create a user account. |
| `POST` | `/auth/login` | Return a JWT bearer token. |
| `GET` | `/assets?address=0x...` | EVM portfolio summary for the provided address. |

Authenticated endpoints require `Authorization: Bearer <token>`:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/auth/me` | Return the authenticated user (includes `role`). |
| `POST` | `/wallet-groups` | Create a wallet group (`name`, optional `description`, `sort_order`). |
| `GET` | `/wallet-groups` | List the authenticated user's wallet groups. |
| `GET` | `/wallet-groups/{id}` | Get a wallet group by ID. |
| `PATCH` | `/wallet-groups/{id}` | Update a wallet group. |
| `DELETE` | `/wallet-groups/{id}` | Delete a wallet group (wallets keep `group_id = NULL`). |
| `POST` | `/wallets` | Add a wallet (`wallet_type`: `evm` or `manual`; EVM requires `address` + supported `chain_type`; manual requires `chain_type=manual`, no address). |
| `GET` | `/wallets` | List active wallets (`?active_only=false` for all). |
| `GET` | `/wallets/{id}` | Get a wallet by ID. |
| `GET` | `/wallets/{id}/assets` | Live EVM portfolio for the wallet address across all supported chains (`total_usd`, per-chain breakdown). |
| `PATCH` | `/wallets/{id}` | Update wallet fields (`label`, `group_id`, `is_active`, `notes`; EVM wallets also `chain_type` and `address`). |
| `DELETE` | `/wallets/{id}` | Soft-delete a wallet (`is_active=false`). |
| `GET` | `/wallets/{id}/balances` | List manual balances for a wallet (`total_usd`, per-asset `value_usd`). |
| `PUT` | `/wallets/{id}/balances` | Upsert manual balances (manual wallets only). |
| `DELETE` | `/wallets/{id}/balances/{asset_id}` | Delete one manual balance row. |
| `POST` | `/snapshot` | Create a snapshot for one active wallet or all active EVM wallets; EVM snapshots aggregate the wallet address across all supported EVM chains. |
| `GET` | `/portfolio?wallet_id=<id>&days=30` | Return snapshot history for a wallet (`total_usd` from multi-chain EVM snapshots). |
| `GET` | `/portfolio/summary` | Return total USD value and top assets from the latest wallet snapshots. |

Supported `chain_type` values for EVM wallets are `mainnet`, `base`, `bnb`,
`arbitrum`, and `linea`. Manual wallets use `chain_type=manual`. Snapshot
collection currently supports EVM wallets only.

Release metadata can be supplied with `APP_VERSION` (defaults to `0.1.0`) and
`BUILD_SHA` (defaults to `unknown`). These non-sensitive values are returned by
`/health`, `/health/live`, and `/health/ready`; `APP_VERSION` is also used for
the OpenAPI `info.version`. Do not put credentials or tokens in these variables.

For existing EVM wallets, `PATCH /wallets/{id}` accepts `chain_type` and
`address` (together or separately). `wallet_type` cannot be changed after
creation; manual wallets cannot switch to an on-chain network.

`GET /wallets/{id}/assets` returns the live USD total and per-chain breakdown
for the wallet address across all EVM networks (`mainnet`, `base`, `bnb`,
`arbitrum`, `linea`). The wallet record still stores one `chain_type` (the
network selected in the UI); the assets endpoint aggregates the same address
on every supported chain. Response shape matches public `GET /assets`.

`POST /snapshot` uses the same multi-chain EVM scope for stored history, so
`GET /portfolio?wallet_id=<id>&days=30` can power a chart of the wallet's
total USD value across all EVM networks over time.

```bash
# Live total across all EVM chains for a wallet
curl http://localhost:8000/wallets/1/assets \
  -H "Authorization: Bearer $TOKEN"

# Change network and address on an EVM wallet
curl -X PATCH http://localhost:8000/wallets/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chain_type":"base","address":"0x..."}'
```

### Manual wallet example

```bash
# Create a manual wallet (no on-chain address)
curl -X POST http://localhost:8000/wallets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"label":"Manual BTC","wallet_type":"manual","chain_type":"manual"}'

# Add or update balances (amount * price_usd → value_usd; null price → 0)
curl -X PUT http://localhost:8000/wallets/1/balances \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"balances":[{"symbol":"BTC","amount":"0.125","price_usd":"68000"}]}'

# List balances and total_usd
curl http://localhost:8000/wallets/1/balances \
  -H "Authorization: Bearer $TOKEN"

# Delete one balance by asset_id
curl -X DELETE http://localhost:8000/wallets/1/balances/1 \
  -H "Authorization: Bearer $TOKEN"
```

If `/assets` is called without the `address` query parameter, the app uses
`EVM1_ADDRESS` from the environment.

### Admin access

New registrations always receive `role=user`. To grant admin after a user
registers:

```bash
python -m app.cli promote-admin user@example.com
```

Exit codes: `0` promoted, `1` user not found, `2` already admin.

Manual SQL fallback:

```sql
UPDATE users SET role = 'admin' WHERE email = 'user@example.com';
```

Interactive API documentation:

- Swagger UI: `/docs`
- ReDoc: `/redoc`

## Environment Variables

Copy the example file before starting the Docker Compose stack:

```bash
cp .env.example .env
```

| Variable | Required | Description |
| --- | --- | --- |
| `APP_ENV` | No | Application environment: `development`, `test`, `staging`, or `production`. Defaults to `development`. `ci` is treated as `test`. |
| `DATABASE_URL` | No | Async PostgreSQL URL. Defaults to `postgresql+asyncpg://wallet:wallet@localhost:5432/wallet`; Docker Compose sets the container URL. |
| `JWT_SECRET` | Staging/Production | Secret used to sign access tokens. Required in staging/production (minimum 32 characters). |
| `JWT_ALG` | No | JWT algorithm. Only `HS256` is allowed. Defaults to `HS256`. |
| `ACCESS_TOKEN_TTL_MIN` | No | Access token lifetime in minutes. Defaults to `60`. |
| `EVM1_ADDRESS` | For default `/assets` address | Default EVM wallet address. |
| `RPC_URL_MAINNET` | For Mainnet aggregation | Comma-separated Ethereum Mainnet RPC URLs. |
| `RPC_URL_BASE` | For Base aggregation | Comma-separated Base RPC URLs. |
| `RPC_URL_BNB` | For BNB aggregation | Comma-separated BNB Chain RPC URLs. |
| `RPC_URL_ARB` | For Arbitrum aggregation | Comma-separated Arbitrum RPC URLs. |
| `RPC_URL_LINEA` | For Linea aggregation | Comma-separated Linea RPC URLs. |

Do not commit `.env`. It is ignored by git.

## JWT Auth Security

`JWT_SECRET` is the symmetric signing key for access tokens (HS256).

**Why the default is dangerous:** this project is open source. A known signing key
lets anyone forge valid tokens if the app runs with that value in production.

**Generate a strong secret:**

```bash
openssl rand -hex 32
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Environment behavior:**

| `APP_ENV` | `JWT_SECRET` | Behavior |
| --- | --- | --- |
| `development` | not set | Uses an implicit dev-only secret and logs a warning. |
| `development` | set explicitly | Must be at least 16 characters and not a known placeholder. |
| `test` | not set | Uses `ci-test-secret` for CI and local test runs. |
| `staging` / `production` | required | Minimum 32 characters; insecure placeholders are rejected at startup. |

**Do not commit `.env`.** Use `.env.example` with placeholders only.

**Verify production config locally:**

```bash
python scripts/check_config_security.py
APP_ENV=production JWT_SECRET="$(openssl rand -hex 32)" \
  python -c "from app.core.config import Settings; Settings(_env_file=None)"
```

Production runtime secrets are managed in the separate `amysyutin/py_wallet-infra`
repository (Kubernetes Secret, not committed to Git).

**Secret rotation:** changing `JWT_SECRET` invalidates all existing access tokens.
Users must log in again. Refresh tokens are not implemented yet; for this
project a hard cutover (change secret, everyone re-authenticates) is sufficient.
For production rotation steps (future), see `amysyutin/py_wallet-infra` and
[`docs/SECURITY_BACKLOG.md`](docs/SECURITY_BACKLOG.md).

## Security CI

Pull requests and main branch builds run additional security checks in a
parallel `security` job:

| Tool | Purpose | Blocks merge |
| --- | --- | --- |
| Gitleaks | Detect secrets in the current repository tree | Yes |
| pip-audit | Dependency vulnerability scan (JSON report) | No (advisory) |
| Bandit | Python SAST on `app/` (JSON report) | No (advisory) |
| `scripts/check_config_security.py` | JWT config fail-fast rules | Yes (in `test` job) |

CI uploads `security-reports` artifacts (`pip-audit-report.json`,
`bandit-report.json`, 14-day retention) even when advisory steps report findings.

**Run locally:**

```bash
# JWT config rules (blocking in CI)
python scripts/check_config_security.py

# Current tree secret scan (same as CI; does not scan full Git history)
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.21.2 detect \
  --source /repo --no-git --redact --config /repo/.gitleaks.toml

# Full Git history audit (manual, one-time; may report historical findings)
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.21.2 detect \
  --source /repo --redact --config /repo/.gitleaks.toml

# Dependency + SAST (pinned in requirements-dev.txt)
pip install -r requirements-dev.txt
pip-audit -r requirements.txt -f json -o pip-audit-report.json
bandit -r app/ -ll -f json -o bandit-report.json
```

Do not widen `.gitleaks.toml` to ignore whole directories (`tests/`, workflows).
Only known fake JWT constants are allowlisted. Triage full-history findings
separately.

Future hardening backlog: [`docs/SECURITY_BACKLOG.md`](docs/SECURITY_BACKLOG.md).

## Running Locally

### Docker Compose

```bash
docker compose up --build -d
docker compose exec app alembic upgrade head
docker compose logs -f app
```

The service will be available at `http://127.0.0.1:8000`.

Stop the stack:

```bash
docker compose down
```

### Python

Start PostgreSQL first. The Docker Compose database can be reused:

```bash
docker compose up -d postgres

python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head

uvicorn app.main:app --reload --port 8000
```

## Testing

Tests require PostgreSQL. Start the local database and run:

```bash
docker compose up -d postgres
pytest -v
```

Run the fast checks used by CI:

```bash
ruff check .
black --check .
pytest -m "not slow and not e2e" -v --tb=short
```

The test suite is designed to run without external network calls or real
secrets. External APIs are mocked in tests.

### Test Markers

- `slow` marks tests that may call real APIs or take longer to run.
- `e2e` marks end-to-end tests that require network access and secrets.

## CI/CD

GitHub Actions contains two workflows:

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `.github/workflows/ci.yml` | Pull request to `main` | Lint, format check, tests, security scans (Gitleaks, pip-audit, Bandit), JWT config checks, Docker Compose smoke test, and Telegram notification on failure. |
| `.github/workflows/main-build.yml` | Push to `main` | Tests, security scans, immutable Docker image build, Compose smoke test, GHCR publish, GitOps image tag update, and Telegram notification. |

The main branch pipeline follows this flow:

```text
test + security -> docker-build -> compose-smoke -> build-and-tag -> bump-gitops -> notify
```

The Docker image is built once, smoke-tested, and published to
`ghcr.io/<repo>:<sha>`. The `bump-gitops` job then updates
`manifests/app/kustomization.yaml` in `amysyutin/py_wallet-infra` and pushes the
new image tag. Kubernetes deployment configuration and cluster reconciliation
are handled outside this application repository.

## GitHub Secrets

| Secret | Used for |
| --- | --- |
| `INFRA_REPO_TOKEN` | Push access to `amysyutin/py_wallet-infra` for GitOps image tag updates. |
| `TELEGRAM_BOT_TOKEN` | Telegram notification bot token. |
| `TELEGRAM_CHAT_ID` | Telegram notification chat ID. |
| `GITHUB_TOKEN` | Automatically provided by GitHub Actions and used to push images to GHCR. |

Runtime application secrets are managed outside this repository and are never
committed to Git.

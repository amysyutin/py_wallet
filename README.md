# py_wallet

FastAPI service for aggregating and monitoring a crypto portfolio.

The app collects balances from EVM networks and Binance, calculates USD values,
and stores wallet snapshots in PostgreSQL. Supported EVM networks are Ethereum
Mainnet, Base, BNB Chain, Arbitrum, and Linea. Binance support covers Spot,
Simple Earn Flexible, and Simple Earn Locked positions.

The application repository contains the service code, database migrations,
tests, Docker image, and CI pipeline. Kubernetes manifests are maintained in the
separate `amysyutin/py_wallet-infra` repository.

## Features

- EVM portfolio aggregation across multiple chains.
- Native token, USDT, and USDC balance tracking.
- Binance Spot and Earn balance aggregation.
- USD valuation through Binance public prices and CoinGecko native token prices.
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
│   ├── config.py                     # EVM, Binance, and token configuration
│   ├── core/
│   │   ├── config.py                 # Database and JWT settings
│   │   └── security.py               # Password hashing and JWT helpers
│   ├── db/
│   │   ├── models/                   # SQLAlchemy models
│   │   └── session.py                # Async database sessions
│   ├── routers/
│   │   ├── auth.py                   # Registration, login, current user
│   │   ├── wallets.py                # User wallet management
│   │   ├── snapshots.py              # Balance snapshot creation
│   │   └── portfolio.py              # Portfolio history and summary
│   ├── connectors/                   # RPC, ERC-20, Binance, and CoinGecko clients
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
| `GET` | `/health` | Database health check. Returns `{"status": "healthy"}` when PostgreSQL is available. |
| `POST` | `/auth/register` | Create a user account. |
| `POST` | `/auth/login` | Return a JWT bearer token. |
| `GET` | `/assets?address=0x...` | EVM portfolio summary for the provided address. |
| `GET` | `/demo/binance/balance` | Demo Binance portfolio (`source: demo`, fixed mock data). |

Authenticated endpoints require `Authorization: Bearer <token>`:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/auth/me` | Return the authenticated user (includes `role`). |
| `POST` | `/wallets` | Add a wallet with `label`, `address`, and `chain_type`. |
| `GET` | `/wallets` | List the authenticated user's wallets. |
| `POST` | `/snapshot` | Create a snapshot for one wallet or all supported EVM wallets. |
| `GET` | `/portfolio?wallet_id=<id>&days=30` | Return snapshot history for a wallet. |
| `GET` | `/portfolio/summary` | Return total USD value and top assets from the latest wallet snapshots. |

Admin endpoints require a JWT for a user with `role=admin` in the database:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/binance/balance` | Real Binance Spot and Earn portfolio summary (signed API). |

Supported `chain_type` values for wallets are `mainnet`, `base`, `bnb`,
`arbitrum`, `linea`, and `binance`. Snapshot collection currently supports EVM
wallets only.

If `/assets` is called without the `address` query parameter, the app uses
`EVM1_ADDRESS` from the environment.

Use `/demo/binance/balance` on public demos and frontends. Do not expose
`/binance/balance` without admin authentication.

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
| `BINANCE_API_KEY` | For Binance API | Binance API key used for signed account requests. |
| `BINANCE_SECRET` | For Binance API | Binance secret used for request signing. |
| `EVM1_ADDRESS` | For default `/assets` address | Default EVM wallet address. |
| `RPC_URL_MAINNET` | For Mainnet aggregation | Ethereum Mainnet RPC URL. |
| `RPC_URL_BASE` | For Base aggregation | Base RPC URL. |
| `RPC_URL_BNB` | For BNB aggregation | BNB Chain RPC URL. |
| `RPC_URL_ARB` | For Arbitrum aggregation | Arbitrum RPC URL. |
| `RPC_URL_LINEA` | For Linea aggregation | Linea RPC URL. |

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
| `.github/workflows/ci.yml` | Pull request to `main` | Lint, format check, tests on Python 3.11 and 3.12, Docker Compose smoke test, and Telegram notification on failure. |
| `.github/workflows/main-build.yml` | Push to `main` | Tests, immutable Docker image build, Compose smoke test, GHCR publish, GitOps image tag update, and Telegram notification. |

The main branch pipeline follows this flow:

```text
test -> docker-build -> compose-smoke -> build-and-tag -> bump-gitops -> notify
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

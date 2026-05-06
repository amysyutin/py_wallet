# py_wallet

FastAPI service for aggregating and monitoring a crypto portfolio.

The app collects balances from EVM networks and Binance, then calculates the USD value of the tracked assets. Supported EVM networks are Ethereum Mainnet, Base, BNB Chain, Arbitrum, and Linea. Binance support covers Spot, Simple Earn Flexible, and Simple Earn Locked positions.

## Features

- EVM portfolio aggregation across multiple chains.
- Native token, USDT, and USDC balance tracking.
- Binance Spot and Earn balance aggregation.
- USD valuation through Binance public prices and CoinGecko native token prices.
- Docker-based local, CI, and production workflows.
- CI checks for linting, formatting, tests, and Docker Compose smoke tests.
- Secret-safe application logging with value redaction.

## Project Structure

```text
py_wallet/
├── app/
│   ├── main.py                       # FastAPI entry point
│   ├── config.py                     # Environment variables, token addresses, RPC config
│   ├── log.py                        # Logging setup with secret redaction
│   ├── models.py                     # Pydantic models
│   ├── routes.py                     # API endpoints
│   ├── connectors/
│   │   ├── rpc.py                    # JSON-RPC calls
│   │   ├── erc20.py                  # ERC-20 balanceOf / decimals helpers
│   │   ├── exchange/
│   │   │   ├── binance.py            # Signed Binance API requests
│   │   │   └── binance_public.py     # Public Binance tickers
│   │   └── price/
│   │       └── coingecko.py          # Native token prices from CoinGecko
│   ├── services/
│   │   ├── portfolio.py              # EVM portfolio aggregation
│   │   └── binance_portfolio.py      # Binance portfolio aggregation
│   └── sources/
│       └── evm.py                    # Manual EVM debugging script
├── tests/
├── .github/workflows/
│   ├── ci.yml                        # PR checks
│   └── main-build.yml                # Main branch build, publish, deploy
├── Dockerfile
├── docker-compose.yml
├── docker-compose.ci.yml
├── docker-compose.prod.yml
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── pytest.ini
```

## API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Basic availability check. Returns `{"status": "ok"}`. |
| `GET` | `/health` | Health check. Returns `{"status": "healthy"}`. |
| `GET` | `/assets?address=0x...` | EVM portfolio summary for the provided address. |
| `GET` | `/binance/balance` | Binance portfolio summary for Spot and Earn balances. |

If `/assets` is called without the `address` query parameter, the app uses `EVM1_ADDRESS` from the environment.

Interactive API documentation is available after startup:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Environment Variables

Create a local `.env` file from the example:

```bash
cp .env.example .env
```

| Variable | Description |
| --- | --- |
| `BINANCE_API_KEY` | Binance API key used for signed account requests. |
| `BINANCE_SECRET` | Binance API secret used for request signing. |
| `EVM1_ADDRESS` | Default EVM wallet address used by `/assets`. |
| `RPC_URL_MAINNET` | Ethereum Mainnet RPC URL. |
| `RPC_URL_BASE` | Base RPC URL. |
| `RPC_URL_BNB` | BNB Chain RPC URL. |
| `RPC_URL_ARB` | Arbitrum RPC URL. |
| `RPC_URL_LINEA` | Linea RPC URL. |

Do not commit `.env`. It is ignored by git.

## Running Locally

### Docker

```bash
docker compose up --build -d
docker compose logs -f
docker compose down
```

The service will be available at `http://127.0.0.1:8000`.

### Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

uvicorn app.main:app --reload --port 8000
```

## Production

Production uses `docker-compose.prod.yml`, which pulls the published image from GHCR instead of building from local sources.

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

The production compose file reads secrets from `/home/shared/cripto_secrets/.env`.

## Testing

Run the full test suite:

```bash
pytest -v
```

Run the same fast checks used by CI:

```bash
ruff check .
black --check .
pytest -m "not slow and not e2e" -v --tb=short
```

Optional coverage command:

```bash
pytest --cov=app --cov-report=term-missing
```

The test suite is designed to run without external network calls or real secrets. External APIs are mocked in tests.

### Test Markers

- `slow` marks tests that may call real APIs or take longer to run.
- `e2e` marks end-to-end tests that require network access and secrets.

## CI/CD

There are two GitHub Actions workflows:

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `.github/workflows/ci.yml` | Pull request to `main` | Lint, format check, tests on Python 3.11 and 3.12, Docker Compose smoke test, Telegram notification on failure. |
| `.github/workflows/main-build.yml` | Push to `main` | Tests, Docker image build, Compose smoke test, GHCR publish, production deploy, Telegram notification. |

The main branch pipeline follows a build-once flow:

```text
docker-build -> compose-smoke -> build-and-tag -> deploy
```

The Docker image is built once, saved as a GitHub artifact, smoke-tested, then tagged and pushed to GHCR.

Compose smoke tests use dummy Binance and wallet values because they only verify startup, `/`, and `/health`. Real application secrets are not needed for those checks.

## GitHub Secrets

The repository workflows use these GitHub secrets:

| Secret | Used for |
| --- | --- |
| `DEPLOY_HOST` | Production SSH host. |
| `DEPLOY_USER` | Production SSH user. |
| `DEPLOY_SSH_KEY` | Production SSH private key. |
| `TELEGRAM_BOT_TOKEN` | Telegram notification bot token. |
| `TELEGRAM_CHAT_ID` | Telegram notification chat ID. |

Runtime application secrets such as `BINANCE_API_KEY`, `BINANCE_SECRET`, and wallet/RPC values are expected in the deployment environment, not in CI smoke tests.

## Logging And Secrets

Application logging is configured in `app/log.py`. Log records pass through a secret redaction filter that masks configured secret values before they are written to stdout/stderr.

Avoid logging raw API responses in production unless the payload is known to be safe. Portfolio balances and wallet addresses can still be sensitive even when they are not API secrets.

## Docker Notes

- Base image: `python:3.12-slim`
- Runtime user: non-root `appuser`
- Application port: `8000`
- Production restart policy: `unless-stopped`
- Production healthcheck: Python `urllib.request`
- Registry image: `ghcr.io/amysyutin/py_wallet`

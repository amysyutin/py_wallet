# py_wallet

FastAPI service for aggregating and monitoring a crypto portfolio.

The app collects balances from EVM networks and Binance, then calculates the USD value of the tracked assets. Supported EVM networks are Ethereum Mainnet, Base, BNB Chain, Arbitrum, and Linea. Binance support covers Spot, Simple Earn Flexible, and Simple Earn Locked positions.

Production runs on a self-hosted **k3s** cluster. Local development uses Docker Compose. Deployment is automated via GitHub Actions with `kubectl` against the cluster.

## Features

- EVM portfolio aggregation across multiple chains.
- Native token, USDT, and USDC balance tracking.
- Binance Spot and Earn balance aggregation.
- USD valuation through Binance public prices and CoinGecko native token prices.
- Local development through Docker Compose.
- Production deployment on Kubernetes (k3s) with rolling updates, healthchecks, TLS, and BasicAuth.
- CI/CD pipeline with build-once flow, smoke tests, and auto-rollback on failure.
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
├── k8s/
│   ├── cluster/                      # Cluster-level resources (Namespace, RBAC, ClusterIssuers)
│   │   ├── namespace.yaml
│   │   ├── rbac-ci-deployer.yaml
│   │   ├── clusterissuer-staging.yaml
│   │   ├── clusterissuer-prod.yaml
│   │   └── kustomization.yaml
│   └── app/                          # Application-level resources
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── ingress.yaml
│       ├── certificate.yaml
│       ├── middleware-redirect-https.yaml
│       ├── configmap.yaml
│       └── kustomization.yaml
├── .github/workflows/
│   ├── ci.yml                        # PR checks
│   └── main-build.yml                # Main branch build, publish, k8s deploy
├── Dockerfile
├── docker-compose.yml                # Local development
├── docker-compose.ci.yml             # CI smoke tests
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

Interactive API documentation:

- Swagger UI: `/docs`
- ReDoc: `/redoc`

In production these endpoints sit behind Traefik Ingress with TLS and BasicAuth. Locally they are reachable on `http://127.0.0.1:8000`.

## Environment Variables

In Kubernetes, runtime configuration is split into a `ConfigMap` (non-sensitive parameters) and a `Secret` (credentials and personal data). Locally, both are read from a single `.env` file.

| Variable | Source in K8s | Description |
| --- | --- | --- |
| `BINANCE_API_KEY` | Secret `py-wallet-secrets` | Binance API key used for signed account requests. |
| `BINANCE_SECRET` | Secret `py-wallet-secrets` | Binance API secret used for request signing. |
| `EVM1_ADDRESS` | Secret `py-wallet-secrets` | Default EVM wallet address used by `/assets`. |
| `RPC_URL_MAINNET` | ConfigMap `py-wallet-config` | Ethereum Mainnet RPC URL (public node). |
| `RPC_URL_BASE` | ConfigMap `py-wallet-config` | Base RPC URL. |
| `RPC_URL_BNB` | ConfigMap `py-wallet-config` | BNB Chain RPC URL. |
| `RPC_URL_ARB` | ConfigMap `py-wallet-config` | Arbitrum RPC URL. |
| `RPC_URL_LINEA` | ConfigMap `py-wallet-config` | Linea RPC URL. |
| `LOG_LEVEL` | ConfigMap `py-wallet-config` | Logging level (default `INFO`). |

For local development, copy the example file:

```bash
cp .env.example .env
```

Do not commit `.env`. It is ignored by git.

## Running Locally

### Docker Compose

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

## Deployment (Kubernetes)

Production runs on a self-hosted **k3s** cluster behind Traefik Ingress with Let's Encrypt TLS.

### Architecture

```
GitHub Actions  ─── push image ───►  GHCR  ───── pull ─────►  k3s Pod
       │                                                          ▲
       └── kubectl set image ──────► Deployment ── ReplicaSet ────┘
                                          │
                                          └──► Service (ClusterIP)
                                                    ▲
                          Browser ─► Ingress (Traefik) ─► Service ─► Pod
                                       │
                                       ├── TLS (cert-manager + Let's Encrypt)
                                       └── BasicAuth middleware
```

### Initial Cluster Setup

Cluster-level resources are managed via Kustomize:

```bash
kubectl apply -k k8s/cluster/
```

This creates:

- Namespace `py-wallet-dev`
- ServiceAccount `ci-deployer` with a restricted Role (read-only for most resources, `patch` on Deployments only)
- ClusterIssuers for Let's Encrypt staging and production

Secrets must be created manually on the cluster, not via Git:

```bash
kubectl -n py-wallet-dev create secret generic py-wallet-secrets \
  --from-literal=BINANCE_API_KEY=... \
  --from-literal=BINANCE_SECRET=... \
  --from-literal=EVM1_ADDRESS=0x...
```

### Application Deployment

```bash
kubectl apply -k k8s/app/
kubectl -n py-wallet-dev rollout status deployment/py-wallet
```

Routine image updates happen automatically via the `main-build.yml` GitHub Actions workflow.

### Manual Rollout

```bash
# Update image to a specific commit:
kubectl -n py-wallet-dev set image deployment/py-wallet \
  py-wallet=ghcr.io/amysyutin/py_wallet:<sha>

# Roll back to the previous revision:
kubectl -n py-wallet-dev rollout undo deployment/py-wallet
```

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

Two GitHub Actions workflows:

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `.github/workflows/ci.yml` | Pull request to `main` | Lint, format check, tests on Python 3.11 and 3.12, Docker Compose smoke test, Telegram notification on failure. |
| `.github/workflows/main-build.yml` | Push to `main` | Tests, Docker image build, Compose smoke test, GHCR publish, Kubernetes deploy with auto-rollback, Telegram notification. |

The main branch pipeline follows a build-once flow:

```text
test → docker-build → compose-smoke → build-and-tag → deploy → notify
```

Steps:

1. **test** — ruff, black, pytest.
2. **docker-build** — image is built once with tag `:<sha>` and saved as an artifact.
3. **compose-smoke** — the same artifact is loaded and started via `docker-compose.ci.yml`; `/health` is checked.
4. **build-and-tag** — image is pushed to GHCR as `ghcr.io/<repo>:<sha>` (immutable tag, no `:latest`).
5. **deploy** — `kubectl set image` against the production Deployment, then `kubectl rollout status`, then a smoke test against the public Ingress. On failure the deploy is rolled back automatically (`kubectl rollout undo`).
6. **notify** — Telegram message with SUCCESS / FAILED / CANCELLED status.

## GitHub Secrets

| Secret | Used for |
| --- | --- |
| `KUBE_CONFIG` | Base64-encoded kubeconfig for the restricted `ci-deployer` ServiceAccount. |
| `TELEGRAM_BOT_TOKEN` | Telegram notification bot token. |
| `TELEGRAM_CHAT_ID` | Telegram notification chat ID. |
| `GITHUB_TOKEN` | Automatically provided by GitHub Actions; used to push images to GHCR. |

Runtime application secrets (`BINANCE_API_KEY`, `BINANCE_SECRET`, wallet/RPC values) live inside the cluster as a Kubernetes `Secret` and are never present in CI.

## Logging And Secrets

Application logging is configured in `app/log.py`. Log records pass through a secret redaction filter that masks configured secret values before they are written to stdout/stderr.

Avoid logging raw API responses in production unless the payload is known to be safe. Portfolio balances and wallet addresses can still be sensitive even when they are not API secrets.

## Docker Notes

- Base image: `python:3.12-slim`
- Runtime user: non-root `appuser`
- Application port: `8000`
- Registry image: `ghcr.io/amysyutin/py_wallet`
- Tagging policy: immutable `:<sha>` only; `:latest` is not used in production.

## Kubernetes Notes

- Distribution: **k3s** (single-node)
- Ingress controller: Traefik (bundled with k3s)
- TLS: cert-manager + Let's Encrypt
- Storage: not used yet (the service is stateless)
- Cluster manifests: see `k8s/cluster/` and `k8s/app/`, applied via Kustomize
- Deployment strategy: `RollingUpdate` with `maxSurge=50%`, `maxUnavailable=0%` (zero downtime)
- Replicas: `2`
- Probes: liveness and readiness on `/health`

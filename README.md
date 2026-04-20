# py_wallet

FastAPI-сервис для агрегации и мониторинга криптовалютного портфеля. Собирает данные с EVM-сетей (Ethereum, Base, BNB Chain, Arbitrum, Linea) и биржи Binance (Spot, Earn Flexible, Earn Locked), рассчитывает USD-стоимость активов.

## Структура проекта

```
py_wallet/
├── app/
│   ├── main.py                       # Точка входа FastAPI
│   ├── config.py                     # Переменные окружения, адреса токенов, RPC
│   ├── models.py                     # Pydantic-модели (Asset, PortfolioSummary и др.)
│   ├── routes.py                     # Эндпоинты API
│   ├── connectors/
│   │   ├── rpc.py                    # JSON-RPC вызовы (eth_getBalance, eth_call)
│   │   ├── erc20.py                  # balanceOf / decimals через eth_call
│   │   ├── exchange/
│   │   │   ├── binance.py            # Подписанные запросы к Binance API
│   │   │   └── binance_public.py     # Публичные тикеры (цены) Binance
│   │   └── price/
│   │       └── coingecko.py          # Курсы нативных токенов через CoinGecko
│   ├── services/
│   │   ├── portfolio.py              # Агрегация портфеля по EVM-сетям
│   │   └── binance_portfolio.py      # Агрегация портфеля Binance
│   └── sources/
│       └── evm.py                    # CLI-скрипт для отладки EVM-портфеля
├── tests/
│   ├── conftest.py                   # Pytest-фикстуры и маркеры
│   ├── test_api.py                   # Интеграционные тесты эндпоинтов (12)
│   ├── test_portfolio.py             # Unit-тесты бизнес-логики Binance (9)
│   ├── test_evm_portfolio.py         # Unit-тесты EVM-портфеля (8)
│   ├── test_connectors.py            # Unit-тесты коннекторов rpc/erc20/coingecko (15)
│   └── test_utils.py                 # Unit-тесты утилит и Pydantic-моделей (22)
├── .github/
│   └── workflows/
│       ├── ci.yml                    # PR → main: тесты + smoke + Telegram
│       └── main-build.yml            # push в main: тесты → build → smoke → GHCR → deploy → Telegram
├── Dockerfile
├── docker-compose.yml                # Локальная разработка (build из исходников)
├── docker-compose.ci.yml             # Compose для smoke-тестов в GitHub Actions
├── docker-compose.prod.yml           # Production (pull из GHCR)
├── requirements.txt                  # Production-зависимости
├── requirements-dev.txt              # Dev/CI-зависимости (ruff, black, pytest, httpx)
├── .dockerignore
├── .env.example
├── .gitignore
└── pytest.ini
```

## API-эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/` | Проверка работоспособности (`{"status": "ok"}`) |
| GET | `/health` | Health-check (`{"status": "healthy"}`) |
| GET | `/assets?address=0x...` | Портфель по EVM-сетям — нативные токены, USDT, USDC |
| GET | `/binance/balance` | Портфель Binance — Spot + Earn Flexible + Earn Locked |

`/assets` — если параметр `address` не передан, используется `EVM1_ADDRESS` из `.env`.

## Переменные окружения

Скопируйте `.env.example` в `.env` и заполните:

```bash
cp .env.example .env
```

| Переменная | Назначение |
|------------|-----------|
| `BINANCE_API_KEY` | API-ключ Binance |
| `BINANCE_SECRET` | Секрет Binance |
| `EVM1_ADDRESS` | EVM-адрес кошелька по умолчанию |
| `RPC_URL_MAINNET` | RPC-URL Ethereum Mainnet |
| `RPC_URL_BASE` | RPC-URL Base |
| `RPC_URL_BNB` | RPC-URL BNB Chain |
| `RPC_URL_ARB` | RPC-URL Arbitrum |
| `RPC_URL_LINEA` | RPC-URL Linea |

## Запуск

### Docker (рекомендуется)

```bash
docker compose up --build -d
docker compose logs -f
docker compose down
```

Сервис будет доступен на `http://127.0.0.1:8000`.

### Production (на сервере)

На сервере используется `docker-compose.prod.yml` — он не собирает образ, а скачивает готовый из GHCR:

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

### Локально (без Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

uvicorn app.main:app --reload --port 8000
```

## Тестирование

**66 тестов** — unit + интеграционные, выполняются за ~0.5 сек без сети и секретов.

```bash
pytest -v

# Только быстрые (для CI)
pytest -m "not slow and not e2e"

# С покрытием
pytest --cov=app --cov-report=term-missing
```

### Структура тестов

| Файл | Тип | Кол-во | Что покрывает |
|------|-----|:------:|---------------|
| `test_utils.py` | Unit | 22 | `to_usdt`, `filter_nonzero`, `_pad_addr_32`, Pydantic-модели |
| `test_connectors.py` | Unit | 15 | `get_balance`, `eth_call`, `balance_of`, `decimals`, CoinGecko-кэш |
| `test_portfolio.py` | Unit | 9 | `summarize_binance_usdt` — happy path, timeout, граничные случаи |
| `test_evm_portfolio.py` | Unit | 8 | `summarize_chain`, `summarize_all` — цепочки, токены, агрегация |
| `test_api.py` | Integration | 12 | Все эндпоинты через `TestClient` — роутинг, сериализация, ошибки |

Все тесты изолированы от внешних API через `unittest.mock.patch`.

### Маркеры

- `@pytest.mark.slow` — тесты с реальными API (не запускаются в CI)
- `@pytest.mark.e2e` — end-to-end тесты (требуют секреты и сеть)

## Документация API

После запуска сервера:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## CI/CD

### Пайплайн

```
PR → ci.yml (lint + test + smoke) → merge → main-build.yml → GHCR → deploy → Telegram
```

### Два workflow

| Workflow | Триггер | Что делает |
|----------|---------|------------|
| [ci.yml](.github/workflows/ci.yml) | PR в `main` | lint → test (matrix 3.11 + 3.12) → compose-smoke → Telegram при падении |
| [main-build.yml](.github/workflows/main-build.yml) | push в `main` | test → docker-build → compose-smoke → push в GHCR → deploy на сервер → Telegram |

### Принцип иммутабельного артефакта

Образ собирается **один раз** в `docker-build`, сохраняется как GitHub Artifact и передаётся по цепочке:

```
docker-build (собрал) → compose-smoke (протестировал) → build-and-tag (запушил в GHCR) → deploy (на сервере)
```

Один и тот же образ на всех этапах. Build once, deploy everywhere.

### Branch Protection

Ветка `main` защищена:
- Требуется PR для мержа
- Требуются зелёные status checks (`test`, `compose-smoke`)
- Запрещён force push
- Линейная история коммитов

### Секреты (Settings → Secrets)

| Секрет | Назначение |
|--------|-----------|
| `BINANCE_API_KEY`, `BINANCE_SECRET` | Binance API |
| `EVM1_ADDRESS` | EVM-адрес |
| `BYBIT_API_KEY`, `BYBIT_SECRET` | Bybit API |
| `OKX_API_KEY`, `OKX_SECRET` | OKX API |
| `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` | SSH-деплой на сервер |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Уведомления в Telegram |

### Локально как в CI

```bash
ruff check .
black --check .
pytest -m "not slow and not e2e" -v --tb=short
```

## Docker-окружение

- **Базовый образ:** `python:3.12-slim`
- **Пользователь:** непривилегированный `appuser`
- **Порт:** `8000`
- **Политика перезапуска:** `unless-stopped`
- **Healthcheck:** через `urllib.request` (curl нет в slim-образе)
- **Registry:** `ghcr.io/amysyutin/py_wallet`

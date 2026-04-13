# Crypto Analyzer

FastAPI-сервис для агрегации и мониторинга криптовалютного портфеля. Собирает данные с EVM-сетей (Ethereum, Base, BNB Chain, Arbitrum, Linea) и биржи Binance (Spot, Earn Flexible, Earn Locked), рассчитывает USD-стоимость активов.

## Структура проекта

```
cripto_analyzer/
├── app/
│   ├── __init__.py
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
│       ├── ci.yml                  # PR → main: тесты + compose-smoke
│       └── main-build.yml          # push в main (+ опционально PR): тесты, docker build, smoke
├── Dockerfile
├── docker-compose.yml
├── docker-compose.ci.yml           # Compose для smoke в GitHub Actions
├── .dockerignore
├── .env.example
├── .gitignore
├── pytest.ini
└── requirements.txt
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
# Сборка и запуск
docker compose up --build -d

# Просмотр логов
docker compose logs -f

# Остановка
docker compose down
```

Сервис будет доступен на `http://127.0.0.1:8000`.

> **Примечание:** `docker-compose.yml` читает `.env` из `/home/cript/cripto_secrets/.env`. Для локальной разработки измените путь `env_file` или используйте `.env` в корне проекта.

### Локально (без Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

## Тестирование

**66 тестов** — unit + интеграционные, выполняются за ~0.5 сек без сети и секретов.

```bash
# Все тесты
pytest -v

# Только быстрые (для CI)
pytest -m "not slow and not e2e"

# Конкретный файл
pytest tests/test_api.py -v

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

Workflow’ы лежат в [`.github/workflows/`](.github/workflows/).

### Когда что запускается

| Событие | [ci.yml](.github/workflows/ci.yml) | [main-build.yml](.github/workflows/main-build.yml) |
|---------|:----------------------------------:|:--------------------------------------------------:|
| Открыт или обновлён **PR в `main`** | да | да (если в `main-build` оставлен триггер `pull_request`) |
| **Push в `main`** (например после merge) | нет | да |

**Практика:** чтобы не дублировать прогон на каждом PR, в `main-build.yml` обычно оставляют только `push` в `main`; проверку перед merge тогда даёт один workflow — `ci.yml`. Если у тебя в `main-build` включён и `pull_request`, и `push`, на PR отработают оба — это осознанный выбор или повод упростить.

### Что делают job’ы

**Общее:** job **test** (matrix Python **3.11** и **3.12**) — `ruff`, `black --check`, `pytest -m "not slow and not e2e"`.

**[ci.yml](.github/workflows/ci.yml):** `test` → **compose-smoke** (`docker compose -f docker-compose.ci.yml up --build`, ожидание `GET /health`, curl к `/` и `/health`).

**[main-build.yml](.github/workflows/main-build.yml):** `test` → **docker-build** (`docker build` без push) → **compose-smoke** (тот же сценарий, что в CI).

Для compose в CI создаётся `.env`; при необходимости задай секреты в репозитории (**Settings → Secrets**).

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

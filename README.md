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
│   ├── conftest.py                   # Pytest-фикстуры
│   ├── test_api.py                   # Тесты эндпоинтов
│   └── test_portfolio.py             # Тесты бизнес-логики Binance
├── Dockerfile
├── docker-compose.yml
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

```bash
# С активированным venv
pytest -v

# Или напрямую
.venv/bin/pytest -v
```

Тесты используют `unittest.mock.patch` для изоляции от внешних API (Binance, RPC, CoinGecko).

## Документация API

После запуска сервера:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## Docker-окружение

- **Базовый образ:** `python:3.12-slim`
- **Пользователь:** непривилегированный `appuser`
- **Порт:** `8000`
- **Политика перезапуска:** `unless-stopped`

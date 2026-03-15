# Крипто-анализатор (Crypto Analyzer)

FastAPI приложение для отслеживания криптовалютных активов из разных источников.

## 📁 Структура проекта

```
cripto_analyzer/
├── app/
│   ├── __init__.py        # Делает app Python-пакетом
│   ├── main.py            # Точка входа, создаёт FastAPI app
│   ├── routes.py          # Эндпоинты API
│   ├── models.py          # Pydantic модели данных
│   └── db.py              # (заглушка) Для работы с БД
├── tests/
│   └── test_api.py        # Pytest тесты
├── .venv/                 # Виртуальное окружение
├── requirements.txt       # Зависимости проекта
└── README.md             # Этот файл

```

## 🎯 Что делает проект

**Текущий функционал:**
1. **Эндпоинт `/`** - проверка работоспособности сервера
2. **Эндпоинт `/assets`** - возвращает список активов (пока mock-данные)

**Планируется:**
- Подключение реальных источников (биржи, кошельки)
- Получение актуальных цен
- История изменения цен
- Аналитика

## 🛠 Как работает код

### 1. main.py - точка входа
```python
from fastapi import FastAPI
app = FastAPI()  # Создаём FastAPI приложение
```
- Создаёт экземпляр FastAPI
- Регистрирует декораторы `@app.get(...)` из routes.py
- Экспортирует `app` для запуска сервера

### 2. routes.py - эндпоинты
```python
from app.main import app  # Импортируем объект app

@app.get("/assets")       # Регистрируем GET /assets
async def get_assets():   # async = асинхронная функция
    return [{"name": "BTC", "price": 5000, "source": "mock"}]
```
- Импортирует `app` из main.py
- Использует декоратор для регистрации эндпоинта
- Возвращает JSON-данные

### 3. models.py - структура данных
```python
class Asset(BaseModel):  # Pydantic модель
    name: str            # Имя актива
    price: float         # Цена
    source: str          # Источник данных
```
- Определяет структуру данных для валидации
- Используется для документации API

### 4. tests/test_api.py - тесты
```python
client = TestClient(app)  # Создаём тестовый клиент

def test_assets():
    response = client.get("/assets")  # Эмулируем GET запрос
    assert response.status_code == 200  # Проверяем статус
```
- `TestClient` - не запускает сервер, просто выполняет код
- `client.get()` - эмулирует HTTP запрос
- `assert` - проверяет результат

## 🚀 Управление проектом

### Установка зависимостей
```bash
# Переходим в директорию проекта
cd cripto_analyzer

# Устанавливаем зависимости в .venv
.venv/bin/pip install -r requirements.txt
```

### Запуск тестов
```bash
cd cripto_analyzer

# Вариант 1: С PYTHONPATH
PYTHONPATH=. .venv/bin/pytest tests/test_api.py -v

# Вариант 2: С активированным venv
source .venv/bin/activate
pytest tests/test_api.py -v
```

### Запуск сервера (разработка)
```bash
cd cripto_analyzer

# Вариант 1: Прямой запуск
.venv/bin/uvicorn app.main:app --reload

# Вариант 2: С активированным venv
source .venv/bin/activate
uvicorn app.main:app --reload
```

### Проверка эндпоинтов
После запуска сервера:
- http://127.0.0.1:8001/ - главная страница
- http://127.0.0.1:8001/assets - список активов
- http://127.0.0.1:8001/docs - Swagger документация (автоматическая!)
- http://127.0.0.1:8001/redoc - ReDoc документация

### Деактивация venv
```bash
deactivate
```

## 📚 Объяснение ключевых терминов

- **FastAPI** - веб-фреймворк для создания API
- **async/await** - асинхронное программирование (быстрые I/O операции)
- **TestClient** - инструмент для тестирования без запуска сервера
- **Pydantic** - валидация данных (проверяет типы автоматически)
- **@app.get()** - декоратор для регистрации GET эндпоинта
- **venv** - изолированное Python окружение для проекта

## 🧪 Как работают тесты

1. `TestClient` импортирует объект `app`
2. `client.get("/")` эмулирует HTTP запрос
3. Возвращается объект `response` с данными
4. `assert` проверяет что всё правильно

## 🎓 Задания для изучения

- Добавить новый эндпоинт `/health` в routes.py
- Написать тест для этого эндпоинта
- Добавить обработку ошибок (try/except)
- Использовать модель Asset для возврата данных

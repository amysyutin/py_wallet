
from unittest.mock import patch
from app.services.binance_portfolio import summarize_binance_usdt

@patch("app.services.binance_portfolio.load_all_price_cached")
@patch("app.services.binance_portfolio.get_account_balances_earn_locked")
@patch("app.services.binance_portfolio.get_account_balances_earn")
@patch("app.services.binance_portfolio.get_account_balances_spot")
@patch("app.services.binance_portfolio.sync_server_time")
def test_simmarize_binance_usdt_success(
    mock_sync_time,
    mock_spot,
    mock_earn,
    mock_earn_locked,
    mock_prices_loader,
    mock_spot_balance,  # Исправлено имя фикстуры (singular)
    mock_prices
):
    # 1. Настраиваем моки (что они должны вернуть)
    mock_spot.return_value = [
        {"asset": "BTC", "free": "0.1", "locked": "0.0"}, # Спот
        {"asset": "USDT", "free": "100", "locked": "0.0"}
    ]
    mock_earn.return_value = [
        {"asset": "ETH", "amount": "1.0"}
    ]
    mock_earn_locked.return_value = []

    mock_prices = {
    'BNBUSDT': 400.0, 
    'BTCUSDT': 50000.0, 
    'ETHUSDT': 3000.0, 
    'USDT': 1.0
    }


    # Функция to_usdt внутри сервиса использует цены. 
    # Поскольку to_usdt импортирована, но использует load_all_price_cached,
    # нам достаточно подменить возвращаемое значение загрузчика цен.
    mock_prices_loader.return_value = mock_prices

    # 2. Вызываем тестируемую функцию
    result = summarize_binance_usdt()

    # 3. Проверяем результат (Asserts)
    assert "assets" in result
    assert "total_usdt" in result
    
    # Проверяем расчеты: 
    # 0.1 BTC * 50000 = 5000
    # 100 USDT * 1 = 100
    # 1.0 ETH * 3000 = 3000
    # Итого: 8100
    assert result["total_usdt"] == 8100.0

    # Проверяем данные
    assets = {item["asset"]: item for item in result["assets"]}
    assert "BTC" in assets
    assert assets["BTC"]["source"] == "spot"
    assert "ETH" in assets
    assert assets["ETH"]["source"] == "earn_flexible"


def test_summarize_binance_usdt_timeout():
    """проверка обработки ошибок"""
    with patch("app.services.binance_portfolio.sync_server_time") as mock_sync:
        mock_sync.side_effect = TimeoutError("Connection failed")



        result = summarize_binance_usdt()

        assert "error" in result
        assert result["total_usdt"] == 0.0
        assert result["error"] == "Connection failed"








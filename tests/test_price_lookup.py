"""PriceLookup tests — parser units + validation + graceful network degradation."""

from app.tools.price_lookup import PriceLookup


def test_crypto_requires_coin():
    assert PriceLookup.get_crypto_price("")["success"] is False


def test_parse_coingecko():
    res = PriceLookup._parse_coingecko("bitcoin", "usd", {"bitcoin": {"usd": 64000.5}})
    assert res["success"] is True
    assert res["price"] == 64000.5


def test_parse_coingecko_missing():
    res = PriceLookup._parse_coingecko("bitcoin", "usd", {"ethereum": {"usd": 1}})
    assert res["success"] is False


def test_stock_requires_symbol():
    assert PriceLookup.get_stock_price("")["success"] is False


def test_parse_stooq():
    csv_text = (
        "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
        "AAPL.US,2026-08-20,16:00:00,220.0,225.0,219.0,224.5,12345678"
    )
    res = PriceLookup._parse_stooq_csv(csv_text, "aapl.us")
    assert res["success"] is True
    assert res["symbol"] == "AAPL.US"
    assert res["close"] == 224.5
    assert res["high"] == 225.0


def test_parse_stooq_invalid_symbol():
    csv_text = "Symbol,Date,Time,Open,High,Low,Close,Volume\nAAPL.US,N/D,N/D,N/D,N/D,N/D,N/D,N/D"
    res = PriceLookup._parse_stooq_csv(csv_text, "aapl.us")
    assert res["success"] is False


def test_parse_stooq_empty():
    assert PriceLookup._parse_stooq_csv("", "x")["success"] is False
    assert PriceLookup._parse_stooq_csv("Symbol,Date\n", "x")["success"] is False


def test_crypto_network_degradation():
    # No internet in sandbox → must return a typed dict, never raise.
    res = PriceLookup.get_crypto_price("bitcoin")
    assert isinstance(res, dict)
    assert "success" in res


def test_stock_network_degradation():
    res = PriceLookup.get_stock_price("aapl.us")
    assert isinstance(res, dict)
    assert "success" in res

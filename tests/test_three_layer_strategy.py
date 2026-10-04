import sys
sys.path.insert(0, "bot")

import pandas as pd

from strategy.three_layer_strategy import ThreeLayerStrategy


def make_candle(**overrides):
    candle = {
        "BTCUSDT_close": 110,
        "BTCUSDT_macro_ma": 100,
        "ETHUSDT_close": 50,
        "ETHUSDT_rsi": 35,
        "ETHUSDT_bb_lower": 45,
        "ETHUSDT_bb_upper": 55,
        "ETHUSDT_macd_cross_up": True,
        "ETHUSDT_macd_cross_down": False,
    }
    candle.update(overrides)
    return pd.Series(candle)


def test_buy_requires_all_three_layers():
    strategy = ThreeLayerStrategy()

    decisions = strategy.decide_actions(
        make_candle(), ["ETHUSDT"], {"ETHUSDT": 0}, 1000
    )

    assert decisions["ETHUSDT"]["action"] == "BUY"


def test_btc_macro_disagreement_blocks_buy():
    strategy = ThreeLayerStrategy()
    candle = make_candle(BTCUSDT_close=90)

    assert strategy.decide_actions(candle, ["ETHUSDT"], {"ETHUSDT": 0}, 1000) == {}


def test_missing_macd_cross_or_execution_zone_blocks_buy():
    strategy = ThreeLayerStrategy()
    wallet = {"ETHUSDT": 0}
    no_cross = make_candle(ETHUSDT_macd_cross_up=False)
    no_zone = make_candle(ETHUSDT_rsi=50, ETHUSDT_close=50)

    assert strategy.decide_actions(no_cross, ["ETHUSDT"], wallet, 1000) == {}
    assert strategy.decide_actions(no_zone, ["ETHUSDT"], wallet, 1000) == {}


def test_bearish_consensus_sells_existing_spot_position():
    strategy = ThreeLayerStrategy()
    candle = make_candle(
        BTCUSDT_close=90,
        ETHUSDT_rsi=65,
        ETHUSDT_macd_cross_up=False,
        ETHUSDT_macd_cross_down=True,
    )

    decisions = strategy.decide_actions(candle, ["ETHUSDT"], {"ETHUSDT": 2}, 0)

    assert decisions["ETHUSDT"]["action"] == "SELL"

def test_indicator_calculation_adds_macro_macd_bands_and_rsi():
    data = pd.DataFrame({
        "BTCUSDT_close": range(1, 41),
        "ETHUSDT_close": range(41, 81),
    })
    strategy = ThreeLayerStrategy(macro_window=5, band_window=5, rsi_window=5)

    result = strategy.calculate_indicators(data, ["ETHUSDT"])

    assert "BTCUSDT_macro_ma" in result
    assert "ETHUSDT_macd_cross_up" in result
    assert "ETHUSDT_bb_lower" in result
    assert "ETHUSDT_rsi" in result
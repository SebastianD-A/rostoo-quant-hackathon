"""BTC-filtered MACD strategy with Bollinger Band and RSI confirmation."""

import pandas as pd


class ThreeLayerStrategy:
    def __init__(
        self,
        macro_window=200,
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        band_window=20,
        band_std=2,
        rsi_window=14,
        fee=0.001,
    ):
        self.macro_window = macro_window
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.band_window = band_window
        self.band_std = band_std
        self.rsi_window = rsi_window
        self.fee = fee

    def calculate_indicators(self, data, currencies):
        data["BTCUSDT_macro_ma"] = data["BTCUSDT_close"].rolling(self.macro_window).mean()

        for currency in currencies:
            close = data[f"{currency}_close"]
            macd = close.ewm(span=self.macd_fast, adjust=False).mean() - close.ewm(
                span=self.macd_slow, adjust=False
            ).mean()
            signal = macd.ewm(span=self.macd_signal, adjust=False).mean()
            data[f"{currency}_macd_cross_up"] = (macd > signal) & (
                macd.shift(1) <= signal.shift(1)
            )
            data[f"{currency}_macd_cross_down"] = (macd < signal) & (
                macd.shift(1) >= signal.shift(1)
            )

            middle = close.rolling(self.band_window).mean()
            deviation = close.rolling(self.band_window).std()
            data[f"{currency}_bb_upper"] = middle + self.band_std * deviation
            data[f"{currency}_bb_lower"] = middle - self.band_std * deviation

            change = close.diff()
            average_gain = change.clip(lower=0).ewm(
                alpha=1 / self.rsi_window,
                min_periods=self.rsi_window,
                adjust=False,
            ).mean()
            average_loss = -change.clip(upper=0).ewm(
                alpha=1 / self.rsi_window,
                min_periods=self.rsi_window,
                adjust=False,
            ).mean()
            relative_strength = average_gain / average_loss
            data[f"{currency}_rsi"] = 100 - (100 / (1 + relative_strength))

        return data

    def decide_actions(self, candle, currencies, wallet, cash):
        decisions = {}
        btc_close = candle["BTCUSDT_close"]
        btc_macro_ma = candle["BTCUSDT_macro_ma"]
        if pd.isna(btc_close) or pd.isna(btc_macro_ma):
            return decisions

            market_up = btc_close > btc_macro_ma
            market_up = market_up is not None and market_up
        flat = [currency for currency in currencies if wallet[currency] == 0]

        for currency in currencies:
            close = candle[f"{currency}_close"]
            rsi = candle[f"{currency}_rsi"]
            if pd.isna(close) or pd.isna(rsi):
                continue

            holding = wallet[currency] > 0
            buy_zone = close <= candle[f"{currency}_bb_lower"] or rsi < 40
            sell_zone = close >= candle[f"{currency}_bb_upper"] or rsi > 60

            if (
                market_up
                and not holding
                and flat
                and candle[f"{currency}_macd_cross_up"]
                and buy_zone
            ):
                budget = cash / len(flat)
                quantity = budget * (1 - self.fee) / close * 0.999
                decisions[currency] = {
                    "action": "BUY",
                    "order_type": "TAKER",
                    "quantity": quantity,
                }
            elif (
                market_up is not None and not market_up
                and holding
                and candle[f"{currency}_macd_cross_down"]
                and sell_zone
            ):
                decisions[currency] = {"action": "SELL", "order_type": "TAKER"}

        return decisions
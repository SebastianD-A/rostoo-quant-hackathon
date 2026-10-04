"""
gold_btc_bot_strat.py  (multi-coin version)
Strategy object for your Backtester (calculate_indicators / decide_actions interface).

It trades EVERY currency you give the Backtester, e.g.

    bt = Backtester(csv_path=ROOT / "bot" / "data" / "binance historical",
                    currencies=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    bt.run(GoldBTCStrategy(gold_csv=bt.csv_path / "PAXGUSDT_1h.csv"))

Each coin gets its own signal from gold_btc_strategy.py (EMA trend + coin/gold ratio crossover +
gold flight-to-safety veto + RSI band + ATR trailing stop). All coins share one pot of cash.
PAXGUSDT is used only as the gold price input; it is never traded.

Passing currencies=["BTCUSDT"] gives exactly the single-coin behaviour from before.

weight_mode (how the pot is shared):
  "split" : each coin's position size is divided by the number of coins, so total exposure
            stays about the same as the single-coin version (the safer default).
  "full"  : each coin is sized as if it were alone; if the total would exceed max_total_exposure
            all positions are scaled down together. More upside, but ETH/SOL move with BTC,
            so drawdowns are bigger.

daily_trade (default ON): guarantees at least one order on every UTC calendar day. If no signal
trade has happened by 12:00 UTC, it sends one small order in the first coin (about 0.1% of equity),
alternating buy and sell so the position barely changes. On the backtest this raised fees by about
$80 over 2.7 years. Set daily_trade=False to switch it off.

Execution notes (matching your Backtester): decisions use the closed candle and fill at that
candle's close, as TAKER (0.1% fee). Sells are listed before buys so freed cash can be reused.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

from gold_btc_strategy import Config, build_features, target_positions

ORDER_TYPE = "TAKER"
FEE_RATE = 0.001          # used only to size buys so a fee never blocks them


class GoldBTCStrategy:
    def __init__(self, gold_csv: Path | str | None = None, symbols: list[str] | None = None,
                 cfg: Config = Config(), weight_mode: str = "split", max_total_exposure: float = 1.0,
                 rebalance_band: float = 0.10, fee_buffer: float = 0.003,
                 daily_trade: bool = True, daily_trade_hour_utc: int = 12,
                 daily_trade_pct: float = 0.001, daily_trade_min_usd: float = 10.0):
        assert weight_mode in ("split", "full")
        # Guaranteed daily trade: if no order has been sent yet on a UTC calendar day, then from
        # daily_trade_hour_utc onwards send one small keep-alive order in the first coin (BTC).
        # Size = daily_trade_pct of equity (at least daily_trade_min_usd). Buys and sells alternate
        # so the position barely moves. Turn it off with daily_trade=False.
        self.daily_trade = daily_trade
        self.daily_trade_hour_utc = daily_trade_hour_utc
        self.daily_trade_pct = daily_trade_pct
        self.daily_trade_min_usd = daily_trade_min_usd
        self._last_trade_day = None
        self._ka_buy = True
        self.gold_csv = Path(gold_csv) if gold_csv else None
        self.symbols = [s.upper() for s in symbols] if symbols else None   # None = all currencies
        self.cfg = cfg
        self.weight_mode = weight_mode
        self.max_total_exposure = max_total_exposure
        self.rebalance_band = rebalance_band     # as a fraction of equity for ONE coin; divided by number of coins
        self.fee_buffer = fee_buffer
        self.active: list[str] = []

    # ---- called once by Backtester.run ------------------------------------------------
    def calculate_indicators(self, data: pd.DataFrame, currencies: list[str]) -> pd.DataFrame:
        self.active = [c for c in (self.symbols or currencies) if c in currencies]
        self._last_trade_day, self._ka_buy = None, True        # fresh state for every run
        idx = pd.to_datetime(data["open_time"], utc=True)
        out = data.copy()

        raw = {}
        gold = None
        for s in self.active:
            px = data[["open_time", f"{s}_open", f"{s}_high", f"{s}_low", f"{s}_close"]].copy()
            px.columns = ["open_time", "open", "high", "low", "close"]
            px = px.set_index(pd.to_datetime(px["open_time"], utc=True)).drop(columns="open_time")
            if gold is None:
                gold = self._load_gold(px.index)
            res = target_positions(build_features(px, gold, self.cfg), self.cfg)
            raw[s] = res["position"].reindex(idx).to_numpy()

        n = max(len(self.active), 1)
        raw_df = pd.DataFrame(raw)
        if self.weight_mode == "split":
            final = raw_df / n
        else:
            total = raw_df.fillna(0).sum(axis=1)
            scale = np.where(total > self.max_total_exposure, self.max_total_exposure / total.replace(0, np.nan), 1.0)
            final = raw_df.mul(scale, axis=0)
        for s in self.active:
            out[f"target_frac_{s}"] = final[s].to_numpy()
        return out

    def _load_gold(self, btc_index: pd.DatetimeIndex) -> pd.DataFrame:
        if self.gold_csv is not None and self.gold_csv.exists():
            g = pd.read_csv(self.gold_csv)
            g["open_time"] = pd.to_datetime(g["open_time"], utc=True)
            g = g.sort_values("open_time").drop_duplicates("open_time").set_index("open_time")
            return g[["close"]].astype(float)
        print("[GoldBTCStrategy] gold file not found: gold filter will be neutral (EMA trend only)")
        return pd.DataFrame({"close": 1.0}, index=btc_index)

    # ---- called every candle by Backtester.run -----------------------------------------
    def decide_actions(self, candle, currencies, wallet, cash):
        prices = {c: float(candle[f"{c}_close"]) for c in currencies}
        equity = cash + sum(wallet[c] * prices[c] for c in currencies)
        n = max(len(self.active), 1)
        band = self.rebalance_band / n
        ka_usd = max(self.daily_trade_min_usd, self.daily_trade_pct * equity)
        dust = 1.5 * ka_usd if self.daily_trade else 0.0       # leftover keep-alive amounts are not "positions"

        sells, buys = {}, {}
        proceeds = 0.0
        for s in self.active:
            target = candle.get(f"target_frac_{s}", np.nan)
            if target is None or np.isnan(target):
                continue
            price, holding = prices[s], float(wallet.get(s, 0.0))
            cur = holding * price / equity if equity > 0 else 0.0
            diff = target - cur
            if target == 0.0 and holding * price > dust:
                sells[s] = {"action": "SELL", "order_type": ORDER_TYPE, "quantity": None}
                proceeds += holding * price * (1 - FEE_RATE)
            elif diff < -band and target > 0:
                qty = min((-diff * equity) / price, holding)
                sells[s] = {"action": "SELL", "order_type": ORDER_TYPE, "quantity": qty}
                proceeds += qty * price * (1 - FEE_RATE)
            elif diff > band:
                buys[s] = diff

        decisions = dict(sells)                          # sells first, so their cash can fund the buys
        avail = cash + proceeds
        for s, diff in sorted(buys.items(), key=lambda kv: -kv[1]):
            price = prices[s]
            spend = min(diff * equity, avail / (1 + FEE_RATE + self.fee_buffer))
            qty = spend / price
            if qty * price > 10:                         # skip dust
                decisions[s] = {"action": "BUY", "order_type": ORDER_TYPE, "quantity": qty}
                avail -= qty * price * (1 + FEE_RATE)
        # --- guaranteed daily trade ----------------------------------------------------------
        if self.daily_trade and self.active:
            ts = pd.Timestamp(candle["open_time"])
            day = ts.date()
            if any(d["action"] != "HOLD" for d in decisions.values()):
                self._last_trade_day = day                      # a normal signal trade already counts for today
            elif self._last_trade_day != day and ts.hour >= self.daily_trade_hour_utc:
                coin = self.active[0]
                price, holding = prices[coin], float(wallet.get(coin, 0.0))
                hv, qty = holding * price, ka_usd / prices[coin]
                if hv < 0.5 * ka_usd:
                    side = "BUY"
                elif hv <= 1.5 * ka_usd:
                    side, qty = "SELL", holding                 # clear leftover keep-alive amount
                else:                                           # a real position: alternate buy/sell
                    side = "BUY" if self._ka_buy else "SELL"
                    self._ka_buy = not self._ka_buy
                if side == "BUY" and qty * price * (1 + FEE_RATE) > avail:
                    side = None                                 # not enough cash for even a small buy
                if side:
                    decisions[coin] = {"action": side, "order_type": ORDER_TYPE, "quantity": qty}
                    self._last_trade_day = day
        for c in currencies:
            decisions.setdefault(c, {"action": "HOLD"})
        return decisions
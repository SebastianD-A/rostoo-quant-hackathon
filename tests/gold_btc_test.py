import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bot" / "backtesting"))
sys.path.insert(0, str(ROOT / "bot" / "strategy"))

from backtester import Backtester
from gold_btc_bot_strat import GoldBTCStrategy

bt = Backtester(csv_path=ROOT / "bot" / "data" / "binance historical",
                currencies=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
bt.run(GoldBTCStrategy(gold_csv=bt.csv_path / "PAXGUSDT_1h.csv"))
df = bt.data
hold = (df["BTCUSDT_close"].iloc[-1] / df["BTCUSDT_close"].iloc[0] - 1) * 100
print(f"Period: {df['open_time'].iloc[0]} to {df['open_time'].iloc[-1]}")
print(f"Buy & hold BTC: {hold:.2f}%")
bt.plot()

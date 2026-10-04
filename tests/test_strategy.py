import sys; sys.path.insert(0, "bot")
from pathlib import Path
from backtesting.backtester import Backtester
from strategy.strategy import MACrossoverStrategy

bt = Backtester(csv_path=Path("bot/data/binance historical"))
bt.run(MACrossoverStrategy(fast=50, slow=200))

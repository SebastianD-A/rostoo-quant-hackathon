import sys; sys.path.insert(0, "bot")
from pathlib import Path
import matplotlib.pyplot as plt
from backtesting.backtester import Backtester
from strategy.strategy import MACrossoverStrategy
from strategy.three_layer_strategy import ThreeLayerStrategy

data_path = Path("bot/data/binance historical")

ma_backtest = Backtester(csv_path=data_path)
print("Moving-average crossover strategy")
ma_backtest.run(MACrossoverStrategy(fast=50, slow=200))

three_layer_backtest = Backtester(csv_path=data_path)
print("\nThree-layer confirmation strategy")
three_layer_backtest.run(ThreeLayerStrategy())


def summarize(backtest):
	values = [entry["portfolio_value"] for entry in backtest.portfolio_history]
	final_equity = values[-1]
	peak = values[0]
	max_drawdown = 0.0
	for value in values:
		peak = max(peak, value)
		max_drawdown = min(max_drawdown, (value - peak) / peak)
	total_return = (final_equity / backtest.starting_cash - 1) * 100
	return final_equity, total_return, max_drawdown * 100, len(backtest.trades)


results = {
	"Moving average": summarize(ma_backtest),
	"Three-layer": summarize(three_layer_backtest),
}
print("\nStrategy comparison")
print("=" * 72)
print(f"{'Strategy':<20}{'Final equity':>16}{'Return':>12}{'Max DD':>12}{'Trades':>12}")
for name, (equity, total_return, max_drawdown, trades) in results.items():
	print(
		f"{name:<20}${equity:>15,.2f}{total_return:>11.2f}%"
		f"{max_drawdown:>11.2f}%{trades:>12}"
	)

plt.figure(figsize=(12, 6))
plt.plot(
	[entry["time"] for entry in ma_backtest.portfolio_history],
	[entry["portfolio_value"] for entry in ma_backtest.portfolio_history],
	label="Moving average",
	linewidth=1.5,
)
plt.plot(
	[entry["time"] for entry in three_layer_backtest.portfolio_history],
	[entry["portfolio_value"] for entry in three_layer_backtest.portfolio_history],
	label="Three-layer",
	linewidth=1.5,
)
plt.title("Strategy Equity Comparison")
plt.xlabel("Date")
plt.ylabel("Portfolio value ($)")
plt.legend()
plt.grid(True, linestyle=":", alpha=0.6)
plt.tight_layout()
plt.show()
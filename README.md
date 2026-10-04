# rostoo-quant-hackathon

This repository contains two rule-based crypto strategies and a historical backtester for comparing their portfolio results. It currently focuses on research and backtesting.

## Setup

Requires Python 3 and the packages: numpy, pandas, requests, matplotlib

```powershell
python -m pip install -r requirements.txt
```

The repository includes hourly BTCUSDT, ETHUSDT, and SOLUSDT historical CSV files under `bot/data/binance historical/`. The default backtest uses these files and starts with $100,000 in cash.

## Run the comparison

From the repository root:

```powershell
python run_ma.py
```

The script runs each strategy with a separate backtester and portfolio, prints each backtest summary, then prints a comparison table with final equity, total return, maximum drawdown, and trade count. It also opens an equity-curve chart with both strategies plotted over time.

## Backtest assumptions and scope

- Input data is Binance spot 1-hour OHLCV.
- The backtester applies a 0.1% taker fee and a 0.05% maker fee; these strategies submit taker orders.
- Decisions use each candle's close and simulated orders execute at that same close. This is a simplified assumption and may make results more optimistic than live execution.
- Positions are long-only. Short opening, margin, leverage, and funding are not simulated.
- The comparison currently reports return and drawdown metrics. Sharpe, Sortino, and Calmar ratios are not yet calculated.

## Project layout

```text
bot/
	backtesting/backtester.py       Portfolio simulation and trade accounting
	config/settings.py              Configuration placeholder
	data/market_data.py              Binance monthly candle downloader
	data/binance historical/         Included 1-hour CSV data
	execution/roostoo_client.py      Roostoo execution module placeholder
	strategy/strategy.py             Moving-average baseline
	strategy/three_layer_strategy.py Three-layer confirmation strategy
run_ma.py                          Runs and compares both strategies
requirements.txt                   Python dependencies
tests/                             Test directory
```

## Market data

The downloader in `bot/data/market_data.py` fetches monthly Binance spot klines for BTCUSDT, ETHUSDT, and SOLUSDT at the 1-hour interval. The CSVs are already included, so downloading data is not required to run the backtest. The downloader's date range is set in its `__main__` block; review that range before running it, as it writes CSVs into the bundled data directory.

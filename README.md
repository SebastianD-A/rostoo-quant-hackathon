# Roostoo Quant Hackathon

This repository contains two rule-based crypto strategies and a historical backtester for comparing their portfolio results. It currently focuses on research and backtesting; it is not yet a live Roostoo trading bot.

## Strategies

### Moving-average crossover

The baseline computes 50-hour and 200-hour simple moving averages for each asset. It buys an asset when the fast average is above the slow average and the asset is not already held. When the fast average falls below the slow average, it sells the holding.

### Three-layer confirmation

The experimental strategy requires three confirmations before opening a long position:

1. **BTC macro filter:** BTCUSDT's close is above its 200-hour simple moving average.
2. **Momentum:** The asset's MACD (12, 26, 9) has just crossed above its signal line.
3. **Entry zone:** The asset is at or below its lower 20-period Bollinger Band (2 standard deviations), or its RSI (14) is below 40.

For an existing holding, the strategy sells when BTC is below its macro average, the asset's MACD crosses below its signal line, and the asset is at or above its upper Bollinger Band or its RSI is above 60. This is an exit from a long spot holding, not an opening short. Although the hackathon rules allow unleveraged spot long and short trading, the current backtester only models long positions and cash.

All indicators use the supplied 1-hour candles. The BTC filter is therefore a 200-hour average, not a 4-hour average.

## Setup

Requires Python 3 and the packages listed in `requirements.txt`.

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

## Hackathon context

The competition asks teams to build autonomous strategies for Roostoo's mock exchange, deploy them on the provisioned AWS environment, and keep trade activity and strategy changes auditable. The supplied rules prohibit high-frequency trading, market making, and arbitrage; allow unleveraged spot long and short positions; and state taker and maker commissions of 0.1% and 0.05%, respectively. The evaluation includes portfolio return and risk-adjusted measures (Sortino, Sharpe, and Calmar), followed by review of rule compliance, repository quality, and strategy implementation.

This repository does **not** currently include a completed Roostoo API client, live order execution, deployment automation, short-position simulation, or the full risk-adjusted scoring metrics. Those components are needed before treating it as a competition-ready autonomous bot. Live competition rules also prohibit manual intervention in trading.
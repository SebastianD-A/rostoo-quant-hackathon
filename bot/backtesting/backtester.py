from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

data = Path(__file__).parent / "binance historical"

class Backtester:
    def __init__(self, csv_path: Path = data, starting_cash: float = 100_000.0, maker_fee: float = 0.0005, taker_fee: float = 0.001, currencies: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]):
        self.csv_path = csv_path
        self.currencies = [c.upper() for c in currencies]

        #money
        self.starting_cash= starting_cash
        self.cash = starting_cash
        self.wallet = {currency: 0.0 for currency in self.currencies}

        #fees
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee

        #history logs
        self.trades = []
        self.portfolio_history = []
        self.data = self._load_data() #market data

    def _load_data(self):
        merged_df = None

        for currency in self.currencies:
            currency_path = self.csv_path / f"{currency}_1h.csv"
            if not currency_path.exists():
                raise FileNotFoundError(f"csv not found for {currency} at {currency_path}")

            df = pd.read_csv(currency_path)
            df["open_time"] = pd.to_datetime(df["open_time"])

            rename_cols = {
                "open": f"{currency}_open",
                "high": f"{currency}_high",
                "low": f"{currency}_low",
                "close": f"{currency}_close",
                "volume": f"{currency}_volume",
            }

            df = df[["open_time", "open", "high", "low", "close", "volume"]].rename(columns=rename_cols)
            df = df.sort_values("open_time").drop_duplicates(subset="open_time")

            for col in [f"{currency}_open", f"{currency}_high", f"{currency}_low", f"{currency}_close", f"{currency}_volume"]:
                df[col] = df[col].astype(float)

            if merged_df is None:
                merged_df = df
            else:
                merged_df = pd.merge(merged_df, df, on="open_time", how="inner")

        return merged_df.sort_values("open_time").reset_index(drop=True)

    def buy(self, price: float, time_stamp, currency:str, order_type:str = "MAKER", quantity: float = None):
        if self.cash <= 0: return # checks if user has cash

        currency = currency.upper()
        fee_rate = (self.maker_fee if order_type.upper() == "MAKER" else self.taker_fee)

        if quantity is None:
            amount_to_spend = self.cash
            fee = amount_to_spend * fee_rate
            amount_after_fee = amount_to_spend - fee
            currency_bought = amount_after_fee / price
            cash_used = self.cash
        
        else:
            gross_cost = quantity * price
            fee = gross_cost * fee_rate
            total_cost = gross_cost + fee

            if total_cost > self.cash:
                print(f"[{time_stamp}] Insufficient cash; Required:{total_cost:.2f}; Available:{self.cash:.2f}")
                return

            currency_bought = quantity
            cash_used = total_cost

        
        self.wallet[currency] += currency_bought
        self.cash -= cash_used

        #logging action
        self.trades.append({
            "time": time_stamp,
            "currency" : currency,
            "side": "BUY",
            "order_type": order_type.upper(),
            "price": price,
            "quantity": currency_bought,
            "fee": fee,
        })

    def sell(self, price: float, time_stamp, currency: str, order_type: str = "MAKER", quantity: float = None):
        currency = currency.upper()
        current_holding = self.wallet.get(currency, 0.0)

        if current_holding <=0: return

        if quantity is None or quantity > current_holding:
            currency_sold = current_holding

        else:
            currency_sold = quantity

        fee_rate = (self.maker_fee if order_type.upper() == "MAKER" else self.taker_fee)

        sale_value = currency_sold * price
        fee = sale_value * fee_rate
        cash_received = sale_value - fee

        self.cash += cash_received
        self.wallet[currency] -= currency_sold

        if self.wallet[currency] < 1e-8:
              self.wallet[currency] = 0.0

        self.trades.append({
                "time": time_stamp,
                "currency": currency,
                "side": "SELL",
                "order_type": order_type.upper(),
                "price": price,
                "quantity": currency_sold,
                "fee": fee,
            })
        
    def get_portfolio_value(self, current_prices: dict):
        currency_value = sum(self.wallet[c] * current_prices[c] for c in self.currencies)
        
        return self.cash + currency_value


    def run(self, strategy_object):
        self.data = strategy_object.calculate_indicators(self.data, self.currencies)

        for i in range(len(self.data)):
            candle = self.data.iloc[i]
            timestamp = candle["open_time"]

            current_prices = {c: candle[f"{c}_close"] for c in self.currencies}

            #query strategy decisions
            decisions = strategy_object.decide_actions(candle = candle,currencies = self.currencies,wallet = self.wallet,cash = self.cash)

            for currency, order_details in decisions.items():
                action = order_details.get("action", "HOLD")
                order_type = order_details.get("order_type", "MAKER")
                quantity = order_details.get("quantity", None)

                if action == "BUY":
                    self.buy(price=current_prices[currency],time_stamp = timestamp,currency = currency,order_type = order_type,quantity = quantity)
                elif action == "SELL":
                    self.sell(price=current_prices[currency],time_stamp = timestamp,currency = currency,order_type = order_type,quantity = quantity)

            current_value = self.get_portfolio_value(current_prices)
            self.portfolio_history.append({"time": timestamp, "portfolio_value": current_value})

        self._print_summary()

    def _print_summary(self):
        history_df = pd.DataFrame(self.portfolio_history)
        final_val = history_df.iloc[-1]["portfolio_value"]
        total_return = ((final_val - self.starting_cash) / self.starting_cash) * 100

        history_df["peak"] = history_df["portfolio_value"].cummax()
        history_df["drawdown"] = (history_df["portfolio_value"] - history_df["peak"]) / history_df["peak"]
        max_dd = history_df["drawdown"].min() * 100

        trades_df = pd.DataFrame(self.trades)

        if not trades_df.empty and "order_type" in trades_df.columns:
            maker_count = len(trades_df[trades_df["order_type"] == "MAKER"])
            taker_count = len(trades_df[trades_df["order_type"] == "TAKER"])
        else:
            maker_count = 0
            taker_count = 0

        print("Results")
        print("="*20)
        print(f"Currencies Traded: {', '.join(self.currencies)}")
        print(f"Starting Wallet: ${self.starting_cash:,.2f}")
        print(f"Final Equity: ${final_val:,.2f}")
        print(f"Net Profit/Loss: ${final_val - self.starting_cash:,.2f}")
        print(f"Total Return: {total_return:.2f}%")
        print(f"Max Drawdown: {max_dd:.2f}%")
        print(f"Total Executions: {len(self.trades)} (Maker: {maker_count} | Taker:{taker_count})")

    def plot(self):
        df = pd.DataFrame(self.portfolio_history)

        plt.figure(figsize=(11, 6))
        plt.plot(df["time"],df["portfolio_value"],label="Multi-Currency Strategy Equity",color="#da0b0b",linewidth=1.5)

        plt.title("Temp")
        plt.xlabel("Date")
        plt.ylabel("Portfolio Value")
        plt.legend(loc="upper left")
        plt.grid(True, linestyle=":", alpha=0.6)
        plt.tight_layout()
        plt.show()
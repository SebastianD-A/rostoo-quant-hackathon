"""
Moving-average crossover strategy 

Rule, checked every hour for each coin:
  - 50 hour average ABOVE 200-hour average -> trend is up   -> hold the coin
  - 50 hour average BELOW 200-hour average -> trend is down -> sell, hold cash

Each coin gets an equal share of the portfolio so one coin can't use up all the cash.
"""


class MACrossoverStrategy:
    def __init__(self, fast=50, slow=200, fee=0.001):
        self.fast = fast
        self.slow = slow
        self.fee = fee

    def calculate_indicators(self, data, currencies):
        for c in currencies:
            close = data[f"{c}_close"]
            data[f"{c}_fast"] = close.rolling(self.fast).mean()
            data[f"{c}_slow"] = close.rolling(self.slow).mean()
        return data

    def decide_actions(self, candle, currencies, wallet, cash):
        decisions = {}
        # coins we don't hold yet share the remaining cash equally
        flat = [c for c in currencies if wallet[c] == 0]

        for c in currencies:
            fast, slow = candle[f"{c}_fast"], candle[f"{c}_slow"]
            if fast != fast or slow != slow:          # NaN: not enough history yet
                continue

            trend_up = fast > slow
            holding = wallet[c] > 0

            if trend_up and not holding and flat:
                budget = cash / len(flat)
                qty = budget * (1 - self.fee) / candle[f"{c}_close"] * 0.999
                decisions[c] = {"action": "BUY", "order_type": "TAKER", "quantity": qty}
            elif not trend_up and holding:
                decisions[c] = {"action": "SELL", "order_type": "TAKER"}
        return decisions

from pathlib import Path
from statsmodels.tsa.stattools import adfuller

import numpy as np
import pandas as pd
import scipy.stats as stats

data = Path(__file__).parent / "binance historical"


class Crypto:

    def __init__(self, name):
        self.name = name
        history = data / f"{name}_1h.csv"
        self.df = pd.read_csv(history)
        self.df = self.df.sort_values("open_time")

        self.val = self.df["close"]
        self.lt_mean = None
        self.meanr_speed = None
        self.volatility = None
        self.adf_statistic = None
        self.adf_p_val = None
        self.z_score = None
        self.half_life = None

    def calc_ou_meanr(self, window=200):

        val = self.val.dropna().tail(window)
        val_change = val.diff().dropna()
        val_prev = val.shift(1).dropna()
        
        val_prev, val_change = val_prev.align(val_change,join="inner")

        slope, intercept = np.polyfit(val_prev, val_change, 1)

        #by hour
        interval = 1

        self.meanr_speed = -slope / interval
        self.lt_mean = intercept / (self.meanr_speed * interval)
        self.volatility = (val_change - (intercept + slope * val_prev)).std() / np.sqrt(interval)

        adf_val = adfuller(val)

        half_life = -np.log(2) / slope
        p_val = adf_val[1]
        statistic = adf_val[0]
        print(self.name)
        print(f"Long Term Mean {self.lt_mean}")
        print(f"Volatility {self.volatility}")

        print(f"ADF statistic {statistic}")
        print(f"ADF P-value {p_val}")

        #values treated as 1 2 or 3, strong, mid, and unlikely evidence.
        print(f"ADF P-value est {'1' if p_val < 0.02 else ( '2' if p_val < 0.10 else '3')}")
        print(f"Slope Value est {'1' if slope < -0.01 else ( '2' if slope < 0.0 else '3')}")
        #values treated as 1 2 or 3, fast, mid, and slow half lives.
        print(f"half-life est {'1' if half_life < 48 else ( '2' if half_life < 120 else '3')}")

        crypto_dict = {
            "name" : self.name,
            "lt_mean" : self.lt_mean,
            "volatility" : self.volatility,
            "adf_statistic" : statistic,
            "adf_p_val": p_val,
            "slope" : slope,
            "half_life" : half_life 
        }

        return crypto_dict

    def calc_z(self):
        z = stats.zscore(self.val)[-1]
        print(z)

class DataEval:
    def __init__(self):
        self.btc = Crypto("BTCUSDT")
        self.eth = Crypto("ETHUSDT")
        self.sol = Crypto("SOLUSDT")

    def evaluate_meanr(self):
        results = [
            self.btc.calc_ou_meanr(),
            self.eth.calc_ou_meanr(),
            self.sol.calc_ou_meanr()
        ]

        return results

a = DataEval()

print(a.evaluate_meanr())






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

    def calc_ou_meanr(self):

        val = self.val.dropna()
        val_change = val.diff().dropna()
        val_prev = val.shift(1).dropna()

        slope, intercept = np.polyfit(val_prev, val_change, 1)

        #by hour
        interval = 1

        self.meanr_speed = -slope / interval
        self.lt_mean = intercept / (self.meanr_speed * interval)
        self.volatility = (val_change - (intercept + slope * val_prev)).std() / np.sqrt(interval)

        adf_val = adfuller(val)

        half_life = -np.log(2) / slope
        p_val = adf_val[1]
        
        print(self.name)
        print(f"Long Term Mean {self.lt_mean}")
        print(f"Volatility {self.volatility}")

        print(f"ADF statistic {adf_val[0]}")
        print(f"ADF P-value {p_val}")

        #values treated as 1 2 or 3, strong, mid, and unlikely evidence.
        print(f"ADF P-value est {'1' if p_val < 0.02 else ( '2' if p_val < 0.10 else '3')}")
        print(f"Slope Value est {'1' if slope < -0.01 else ( '2' if slope < 0.0 else '3')}")
        #values treated as 1 2 or 3, fast, mid, and slow half lives.
        print(f"half-life est {'1' if half_life < 48 else ( '2' if slope < 120 else '3')}")

    def calc_z(self):
        z = stats.zscore(self.val)[-1]
        print(z)



btc = Crypto("BTCUSDT")
eth = Crypto("ETHUSDT")
sol = Crypto("SOLUSDT")

sol.calc_ou_meanr()

btc.calc_ou_meanr()

eth.calc_ou_meanr()




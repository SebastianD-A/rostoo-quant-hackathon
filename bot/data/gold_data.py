import sys
import time
from pathlib import Path

import pandas as pd
import requests

# usage: python3 bot/data/download_gold.py "path/to/BTCUSDT_1h.csv"
btc_csv = Path(__file__).parent / "binance historical" / "BTCUSDT_1h.csv"

btc = pd.read_csv(btc_csv)
col = btc["open_time"]
t = pd.to_datetime(col, unit="ms") if pd.api.types.is_numeric_dtype(col) else pd.to_datetime(col)
start = int(t.min().tz_localize("UTC").timestamp() * 1000)
end = int(t.max().tz_localize("UTC").timestamp() * 1000)

rows = []
while start <= end:
    r = requests.get(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": "PAXGUSDT", "interval": "1h", "startTime": start, "endTime": end, "limit": 1000},
        timeout=30,
    )
    r.raise_for_status()
    batch = r.json()
    if not batch:
        break
    rows += batch
    start = batch[-1][0] + 3_600_000
    time.sleep(0.2)

df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume",
                                 "ct", "qv", "n", "tb", "tq", "ig"])
df["open_time"] = pd.to_datetime(df["open_time"], unit="ms").dt.strftime("%Y-%m-%d %H:%M:%S")
out = btc_csv.parent / "PAXGUSDT_1h.csv"
df[["open_time", "open", "high", "low", "close", "volume"]].to_csv(out, index=False)
print(f"saved {len(df)} rows to {out}")
from __future__ import annotations
import argparse, json, logging, math, os, sys, time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.config import settings                              # noqa: E402
from bot.execution.roostoo_client import RoostooClient       # noqa: E402

COINS = ["BTC", "ETH", "SOL"]
GOLD = "PAXGUSDT"             # gold price input for the gold strategy (signal only, never traded)
BINANCE_HOSTS = ["https://api.binance.com", "https://data-api.binance.vision", "https://api.binance.us"]
N_BARS = 1000                 # Binance max; the strategy needs 200

CASH_RESERVE_USD = 100.0      # never let the strategy spend the last $100 (keeps keep-alive trades possible)
DUST_USD = 50.0               # holdings worth less than this are treated as "not holding" (keep-alive leftovers)
KEEPALIVE_AFTER_HOURS = 20.0  # no trade for this long -> send a small one (so any 24h window has a trade)
KEEPALIVE_USD = 20.0          # size of the keep-alive trade
STATE_DIR = Path(os.environ.get("BOT_STATE_DIR", ROOT / "state"))
STATE_FILE = STATE_DIR / "bot_state.json"

log = logging.getLogger("live_runner")


def sym(c: str) -> str:
    return f"{c}USDT"


def pair(c: str) -> str:
    return f"{c}/USD"


# ------------------------------------------------------------------ market data
def fetch_klines(symbol: str, n: int = N_BARS) -> pd.DataFrame:
    err = None
    for host in BINANCE_HOSTS:
        try:
            r = requests.get(f"{host}/api/v3/klines",
                             params={"symbol": symbol, "interval": "1h", "limit": n}, timeout=20)
            r.raise_for_status()
            df = pd.DataFrame(r.json(), columns=["open_time", "open", "high", "low", "close", "volume",
                                                 "close_time", "qv", "nt", "tb", "tq", "ig"])
            df = df[["open_time", "open", "high", "low", "close", "volume", "close_time"]].astype(float)
            df = df[df["close_time"] < time.time() * 1000]            # closed candles only
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            return df.drop(columns="close_time").reset_index(drop=True)
        except Exception as e:
            err = e
    raise RuntimeError(f"could not fetch {symbol} candles from any host: {err}")


def build_wide(frames: dict) -> pd.DataFrame:
    """Same layout your Backtester gives the strategy: open_time, BTCUSDT_close, ETHUSDT_close, ..."""
    wide = None
    for s, df in frames.items():
        d = df[["open_time", "open", "high", "low", "close"]].copy()
        d.columns = ["open_time"] + [f"{s}_{c}" for c in ("open", "high", "low", "close")]
        wide = d if wide is None else wide.merge(d, on="open_time", how="inner")
    return wide.sort_values("open_time").reset_index(drop=True)


# ------------------------------------------------------------------ state
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(st: dict):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(st))
    except Exception as e:
        log.warning("could not save state: %s", e)


# ------------------------------------------------------------------ orders
def floor_to(x: float, decimals: int) -> float:
    f = 10 ** decimals
    return math.floor(x * f + 1e-9) / f


def send(client, info, live, coin, side, qty, price):
    """Place one MARKET order. Returns True if it was accepted (or would be, in dry run)."""
    meta = info.get("TradePairs", {}).get(pair(coin), {})
    if meta and not meta.get("CanTrade", True):
        log.warning("%s is not tradable right now - skipped", pair(coin))
        return False
    qty = floor_to(float(qty), int(meta.get("AmountPrecision", 4)))
    value = qty * price
    if qty <= 0 or value < float(meta.get("MiniOrder", 1.0)):
        log.info("%s %s too small (qty %s = $%.2f) - skipped", side, pair(coin), qty, value)
        return False
    if not live:
        log.info("[DRY RUN] would %s %s %s (~$%.2f)", side, qty, pair(coin), value)
        return True
    try:
        res = client.place_order(pair(coin), side, qty, order_type="MARKET")
    except Exception as e:
        log.error("ORDER ERROR %s %s: %s", side, pair(coin), e)
        return False
    if res.get("Success"):
        od = res.get("OrderDetail", {})
        log.info("ORDER OK %s %s %s -> %s, filled %s @ %s", side, qty, pair(coin),
                 od.get("Status"), od.get("FilledQuantity"), od.get("FilledAverPrice"))
        return True
    log.error("ORDER REJECTED %s %s %s: %s", side, qty, pair(coin), res.get("ErrMsg"))
    return False


# ------------------------------------------------------------------ one cycle
def make_strategy(name: str):
    if name == "ma":
        from bot.strategy.strategy import MACrossoverStrategy
        return MACrossoverStrategy()
    if name == "three":
        from bot.strategy.three_layer_strategy import ThreeLayerStrategy
        return ThreeLayerStrategy()
    # gold: your gold_btc_bot_strat.py imports its sibling gold_btc_strategy.py by plain name
    sys.path.insert(0, str(ROOT / "bot" / "strategy"))
    from gold_btc_bot_strat import GoldBTCStrategy
    # the runner has its own keep-alive, so the strategy's built-in daily trade is switched off
    return GoldBTCStrategy(gold_csv=STATE_DIR / "paxg_live.csv", daily_trade=False)


def run_cycle(client, strat, info, live, state):
    currencies = [sym(c) for c in COINS]

    # 1) indicators from hourly history
    wide = build_wide({sym(c): fetch_klines(sym(c)) for c in COINS})
    if hasattr(strat, "gold_csv"):                               # gold strategy needs the gold price history
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        fetch_klines(GOLD)[["open_time", "close"]].to_csv(strat.gold_csv, index=False)
    data = strat.calculate_indicators(wide.copy(), currencies)
    candle = data.iloc[-1].copy()

    # 2) live prices + real account from Roostoo
    prices = {}
    for c in COINS:
        t = client.get_ticker(pair(c))
        prices[c] = float(t["Data"][pair(c)]["LastPrice"])
        candle[f"{sym(c)}_close"] = prices[c]
    bal = client.get_balance()
    if not bal.get("Success", True):
        raise RuntimeError(f"balance failed: {bal.get('ErrMsg')}")
    w = bal.get("SpotWallet") or bal.get("Wallet") or {}
    cash = float(w.get("USD", {}).get("Free", 0.0))
    held = {c: float(w.get(c, {}).get("Free", 0.0)) for c in COINS}
    equity = cash + sum(held[c] * prices[c] for c in COINS)

    # 3) strategy decisions (tiny leftovers count as "not holding")
    wallet = {sym(c): (held[c] if held[c] * prices[c] >= DUST_USD else 0.0) for c in COINS}
    decisions = strat.decide_actions(candle, currencies, wallet, max(cash - CASH_RESERVE_USD, 0.0))
    log.info("bar %s | equity $%.2f cash $%.2f | holdings %s | decisions %s",
             candle["open_time"], equity, cash, {c: round(held[c], 6) for c in COINS},
             {k: v.get("action") for k, v in decisions.items()} or "none")

    traded = False
    orders = [(k, v) for k, v in decisions.items() if v.get("action") in ("BUY", "SELL")]
    for k, v in sorted(orders, key=lambda kv: kv[1]["action"] != "SELL"):       # sells first
        c = k.replace("USDT", "")
        qty = held[c] if v["action"] == "SELL" else v.get("quantity")
        traded |= send(client, info, live, c, v["action"], qty, prices[c])

    # 4) keep-alive: make sure there is a trade at least every ~20h
    now = time.time()
    last = state.get("last_trade_ts")
    if not traded and (last is None or now - last >= KEEPALIVE_AFTER_HOURS * 3600):
        c, p = COINS[0], prices[COINS[0]]
        mini = float(info.get("TradePairs", {}).get(pair(c), {}).get("MiniOrder", 1.0))
        ka_usd = max(KEEPALIVE_USD, 1.5 * mini)
        hv = held[c] * p
        if hv < DUST_USD:
            side = "SELL" if hv >= max(5.0, 1.1 * mini) else "BUY"      # clear last keep-alive leftover, else buy a bit
        else:
            side = "BUY" if state.get("ka_buy", True) else "SELL"
            state["ka_buy"] = not state.get("ka_buy", True)
        if side == "BUY" and cash < ka_usd * 1.01:
            side = "SELL" if hv >= ka_usd else None
        if side:
            qty = held[c] if (side == "SELL" and hv < DUST_USD) else ka_usd / p
            log.info("keep-alive trade: %s ~$%.0f of %s", side, ka_usd, pair(c))
            traded |= send(client, info, live, c, side, qty, p)

    if traded and live:
        state["last_trade_ts"] = now
    save_state(state)


def sleep_to_next_hour(extra_s: int = 30):
    now = time.time()
    time.sleep(max(1, (int(now // 3600) + 1) * 3600 + extra_s - now))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="really place orders (default: dry run)")
    ap.add_argument("--once", action="store_true", help="run one cycle and exit")
    ap.add_argument("--strategy", choices=["gold", "ma", "three"], default="gold",
                    help="gold = BTC/gold strategy (default); ma = 50/200 moving-average crossover; "
                         "three = three-layer MACD/Bollinger/RSI strategy")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    client = RoostooClient(api_key=settings.ROOSTOO_API_KEY, secret_key=settings.ROOSTOO_SECRET_KEY,
                           base_url=settings.ROOSTOO_BASE_URL)
    info = client.get_exchange_info()
    log.info("exchange running=%s | mode=%s", info.get("IsRunning"), "LIVE" if args.live else "DRY RUN")
    missing = [pair(c) for c in COINS if pair(c) not in info.get("TradePairs", {})]
    if missing:
        sys.exit(f"pairs not on the exchange: {missing}")

    strat, state = make_strategy(args.strategy), load_state()
    log.info("strategy: %s", args.strategy)
    while True:
        try:
            run_cycle(client, strat, info, args.live, state)
        except Exception as e:                       # never die; log and try again next hour
            log.exception("cycle failed: %s", e)
        if args.once:
            break
        sleep_to_next_hour()


if __name__ == "__main__":
    main()
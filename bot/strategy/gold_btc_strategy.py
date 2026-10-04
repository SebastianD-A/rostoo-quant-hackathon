"""
gold_btc_strategy.py
Short-term, long-only BTC strategy for the Roostoo spot simulator.

Idea
----
1. TREND      : BTC fast/slow EMA crossover on hourly closes (the core signal).
2. GOLD       : BTC/XAU ratio fast/slow EMA crossover. If the ratio is trending up,
                BTC is outperforming gold (risk-on). That is the "crossover divergence"
                confirmation. A gold filter only vetoes entries when gold is surging
                AND BTC has historically moved against gold (negative rolling corr),
                i.e. a flight-to-safety regime.
3. MOMENTUM   : RSI band so we don't buy exhausted spikes.
4. RISK       : ATR trailing stop, volatility-scaled position size, cooldown after exit.

Weekends: gold futures/spot are closed, so gold data is stale. On weekends (or when gold
has not updated) the gold filter is NEUTRAL: it neither confirms nor vetoes, and the
trend signal must be stronger (wider EMA gap) to enter.

Pure functions only. No API calls here, so it plugs into any execution layer
(Roostoo POST /v3/place_order, etc.).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd


@dataclass
class Config:
    # trend
    fast: int = 24                      # tuned (was 12)
    slow: int = 192                     # tuned (was 48): slower trend = far fewer trades
    min_gap: float = 0.0015          # EMA gap (fast/slow - 1) required to enter
    weekend_extra_gap: float = 0.0015
    # gold
    ratio_fast: int = 24
    ratio_slow: int = 96
    corr_window: int = 24 * 14       # 14d of hourly bars
    gold_surge_z: float = 1.0        # gold 24h return z-score treated as a surge
    gold_ret_window: int = 24
    gold_z_window: int = 24 * 30
    veto_corr: float = -0.1          # veto only if corr below this
    # momentum
    rsi_len: int = 14
    rsi_min: float = 50.0
    rsi_max: float = 75.0
    # risk
    atr_len: int = 24
    atr_stop_mult: float = 6.0          # tuned (was 2.5): wide stop, stops whipsaw exits
    target_vol_per_bar: float = 0.004   # target hourly risk for sizing
    max_position: float = 1.0           # fraction of equity
    min_position: float = 0.25
    cooldown_bars: int = 24             # tuned (was 6)
    weekend_stale: bool = False         # True only for gold feeds that close on weekends (XAU spot/futures). PAXG trades 24/7.
    use_gold: bool = True               # False = pure EMA trend (for comparison)
    extra: dict = field(default_factory=dict)


def _rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _atr(df: pd.DataFrame, n: int) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def build_features(btc: pd.DataFrame, gold: pd.DataFrame, cfg: Config = Config()) -> pd.DataFrame:
    """
    btc  : hourly DataFrame indexed by UTC timestamp with columns open, high, low, close.
    gold : hourly (or coarser) DataFrame indexed by UTC timestamp with column close
           (XAUUSD spot, GC=F, or GLD). Forward-filled onto the BTC index.
    Gold at bar t is shifted by one bar so we never use information not yet available.
    """
    df = btc[["open", "high", "low", "close"]].copy()

    g_raw = gold["close"].reindex(df.index.union(gold.index)).sort_index()
    g_fresh = g_raw.notna().reindex(df.index).fillna(False)
    g = g_raw.ffill().reindex(df.index)
    # staleness: gold unchanged for > 6 bars (weekend / holiday / feed gap)
    stale = (g.diff().abs() == 0).rolling(6).sum().fillna(0) >= 6
    df["gold"] = g.shift(1)
    df["gold_stale"] = stale.shift(1).fillna(True)
    if cfg.weekend_stale:
        df["gold_stale"] = df["gold_stale"] | df.index.dayofweek.isin([5, 6])

    c = df["close"]
    df["ema_f"] = c.ewm(span=cfg.fast, adjust=False).mean()
    df["ema_s"] = c.ewm(span=cfg.slow, adjust=False).mean()
    df["gap"] = df["ema_f"] / df["ema_s"] - 1

    ratio = c / df["gold"]
    df["ratio_f"] = ratio.ewm(span=cfg.ratio_fast, adjust=False).mean()
    df["ratio_s"] = ratio.ewm(span=cfg.ratio_slow, adjust=False).mean()
    df["ratio_up"] = df["ratio_f"] > df["ratio_s"]

    btc_ret = c.pct_change()
    gold_ret = df["gold"].pct_change()
    df["corr"] = btc_ret.rolling(cfg.corr_window).corr(gold_ret)
    g24 = df["gold"].pct_change(cfg.gold_ret_window)
    z = (g24 - g24.rolling(cfg.gold_z_window).mean()) / g24.rolling(cfg.gold_z_window).std()
    df["gold_z"] = z

    df["rsi"] = _rsi(c, cfg.rsi_len)
    df["atr"] = _atr(df, cfg.atr_len)
    return df


def gold_state(row: pd.Series, cfg: Config) -> str:
    """'confirm' | 'neutral' | 'veto'"""
    if row["gold_stale"] or np.isnan(row["corr"]) or np.isnan(row["gold_z"]):
        return "neutral"
    if row["gold_z"] > cfg.gold_surge_z and row["corr"] < cfg.veto_corr:
        return "veto"            # flight to safety: gold surging, BTC trades inversely
    if row["ratio_up"]:
        return "confirm"         # BTC outperforming gold
    return "neutral"


def target_positions(df: pd.DataFrame, cfg: Config = Config()) -> pd.DataFrame:
    """
    Walks the bars and returns df with columns:
      position (0..max_position, fraction of equity to hold AFTER this bar's close),
      reason   (why the position changed).
    Same logic as before, rewritten on numpy arrays so it runs ~20x faster.
    """
    n = len(df)
    close = df["close"].to_numpy(float)
    ema_f = df["ema_f"].to_numpy(float)
    ema_s = df["ema_s"].to_numpy(float)
    gap = df["gap"].to_numpy(float)
    atr = df["atr"].to_numpy(float)
    rsi = df["rsi"].to_numpy(float)
    corr = df["corr"].to_numpy(float)
    gz = df["gold_z"].to_numpy(float)
    stale = df["gold_stale"].to_numpy(bool)
    ratio_up = df["ratio_up"].to_numpy(bool)

    # gold state per bar: 0 neutral, 1 confirm, -1 veto
    gs = np.zeros(n, dtype=int)
    if cfg.use_gold:
        valid = ~(stale | np.isnan(corr) | np.isnan(gz))
        veto = valid & (gz > cfg.gold_surge_z) & (corr < cfg.veto_corr)
        confirm = valid & ~veto & ratio_up
        gs[veto] = -1
        gs[confirm] = 1

    pos = np.zeros(n)
    reasons = [""] * n
    in_pos, stop, peak, cool, size = False, np.nan, np.nan, 0, 0.0

    for i in range(n):
        if np.isnan(ema_s[i]) or np.isnan(atr[i]) or i < cfg.slow + 2:
            continue
        price = close[i]
        cross_up = ema_f[i - 1] <= ema_s[i - 1] and ema_f[i] > ema_s[i]
        trend_up = ema_f[i] > ema_s[i]
        g = gs[i]

        if in_pos:
            peak = max(peak, price)
            stop = max(stop, peak - cfg.atr_stop_mult * atr[i])
            exit_reason = None
            if price < stop:
                exit_reason = "atr_stop"
            elif not trend_up:
                exit_reason = "ema_cross_down"
            elif g == -1:
                exit_reason = "gold_flight_to_safety"
            if exit_reason:
                in_pos, cool, size = False, cfg.cooldown_bars, 0.0
                reasons[i] = exit_reason
            else:
                pos[i] = size
                continue

        if cool > 0:
            cool -= 1
            continue

        if cfg.use_gold:
            need_gap = cfg.min_gap + (cfg.weekend_extra_gap if stale[i] else 0.0)
            gold_ok = g != -1 and (g == 1 or stale[i] or cross_up)
        else:
            need_gap = cfg.min_gap
            gold_ok = True
        enter = (
            trend_up
            and gap[i] > need_gap
            and gold_ok
            and cfg.rsi_min <= rsi[i] <= cfg.rsi_max
        )
        if enter:
            vol = max(atr[i] / price, 1e-6)
            size = float(np.clip(cfg.target_vol_per_bar / vol * 0.5, cfg.min_position, cfg.max_position))
            in_pos, peak = True, price
            stop = price - cfg.atr_stop_mult * atr[i]
            pos[i] = size
            reasons[i] = f"enter_{'confirm' if g == 1 else 'neutral'}" if cfg.use_gold else "enter_trend"

    out = df.copy()
    out["position"] = pos
    out["reason"] = reasons
    return out


def latest_signal(btc: pd.DataFrame, gold: pd.DataFrame, cfg: Config = Config()) -> dict:
    """Convenience for the live loop: returns the target fraction of equity in BTC now."""
    res = target_positions(build_features(btc, gold, cfg), cfg)
    last = res.iloc[-1]
    return {
        "time": res.index[-1],
        "target_fraction": float(last["position"]),
        "reason": last["reason"],
        "gold_state": gold_state(res.iloc[-1], cfg),
        "gap": float(last["gap"]),
        "rsi": float(last["rsi"]),
    }
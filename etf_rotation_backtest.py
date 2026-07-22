#!/usr/bin/env python3
"""
DMG Capital — ETF Rotation Backtest
Signal : CallingMarkets 2-of-3 (EMA20>EMA55, RSI14>EMA14, MACD>Signal) on monthly bars
Universe: 9-asset macro rotation basket including Bitcoin
Weighting: Equal weight among BUY signals; BTC capped at 20%; BIL (cash) when no signals
Data    : yfinance — ETFs via monthly interval, BTC-USD via daily resampled to monthly
Outputs : etf_rotation_results.json, etf_rotation_results.md
"""

import json
import math
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

# ── Universe ──────────────────────────────────────────────────────────────────
UNIVERSE = {
    "SPY":     "US Large Cap (S&P 500)",
    "QQQ":     "US Tech / Nasdaq 100",
    "IWM":     "US Small Cap (Russell 2000)",
    "EEM":     "Emerging Markets",
    "TLT":     "Long-Term Treasuries (20yr+)",
    "SHY":     "Short-Term Treasuries (1-3yr)",
    "GLD":     "Gold",
    "DJP":     "Broad Commodities",
    "BTC-USD": "Bitcoin",
}

# No cash proxy — when nothing is BUY the portfolio sits in real cash (0%)
BTC_CAP       = 0.20      # Bitcoin capped at 20% regardless of signal
COMMISSION    = 0.001     # 0.1% per trade (realistic for ETFs)
START_CAPITAL = 100_000

# ── Helpers ───────────────────────────────────────────────────────────────────
def strip_tz(idx):
    """Remove timezone from DatetimeIndex safely — works whether tz-aware or naive."""
    return idx.tz_convert(None) if idx.tz is not None else idx

def to_series_1d(obj):
    """Guarantee a 1-D float Series. Handles DataFrame, multi-column, or plain Series."""
    if isinstance(obj, pd.DataFrame):
        obj = obj.iloc[:, 0]
    return obj.squeeze().astype(float)

def normalize_index(prices):
    """Snap any DatetimeIndex to month-start, strip timezone, deduplicate."""
    s = prices.copy()
    s.index = strip_tz(s.index)
    s.index = s.index.to_period("M").to_timestamp()   # no freq arg → start of period
    return s[~s.index.duplicated(keep="last")]

# ── Indicators (mirrors Pine Script 2-of-3 signal exactly) ───────────────────
def calc_ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def calc_rma(s, n):
    return s.ewm(alpha=1 / n, adjust=False).mean()

def calc_rsi(s, n=14):
    d    = s.diff()
    gain = calc_rma(d.clip(lower=0), n)
    loss = calc_rma((-d).clip(lower=0), n)
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))

def signals(close):
    """Return per-bar signal DataFrame for one ticker."""
    close    = to_series_1d(close)
    ema20    = calc_ema(close, 20)
    ema55    = calc_ema(close, 55)
    rsi14    = calc_rsi(close, 14)
    rsi_ma   = calc_ema(rsi14, 14)
    macd     = calc_ema(close, 12) - calc_ema(close, 26)
    sig_line = calc_ema(macd, 9)

    bull1  = ema20 > ema55
    bull2  = rsi14 > rsi_ma
    bull3  = macd  > sig_line
    score  = bull1.astype(int) + bull2.astype(int) + bull3.astype(int)
    is_buy = score >= 2

    return pd.DataFrame({
        "close":  close,
        "score":  score,
        "is_buy": is_buy,
    }, index=close.index)

# ── Data fetch ────────────────────────────────────────────────────────────────
def fetch_monthly(tickers, start="2003-01-01"):
    """
    Download monthly close prices.
    ETFs  : yfinance monthly interval (already month-start, tz-naive).
    BTC   : yfinance daily interval resampled to month-end, then normalised.
    Returns dict of {ticker: pd.Series} with raw (un-normalised) indexes.
    Normalisation happens inside run_backtest() so all indexes align.
    """
    result      = {}
    etf_tickers = [t for t in tickers if t != "BTC-USD"]

    # ── ETFs ──────────────────────────────────────────────────────────────────
    print(f"Fetching ETF monthly data: {etf_tickers}")
    raw = yf.download(etf_tickers, start=start, interval="1mo",
                      auto_adjust=True, progress=False)

    # yfinance 1.5.x always returns MultiIndex columns
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw[["Close"]].rename(columns={"Close": etf_tickers[0]})

    closes = closes.iloc[:-1]   # drop incomplete current month
    print(f"  ETFs: {len(closes)} months  "
          f"({closes.index[0].date()} → {closes.index[-1].date()})")

    for t in etf_tickers:
        if t in closes.columns:
            s = to_series_1d(closes[[t]]).dropna()
            if len(s) > 0:
                result[t] = s

    # ── BTC-USD ───────────────────────────────────────────────────────────────
    if "BTC-USD" in tickers:
        print("Fetching BTC-USD daily data (resampling to monthly)...")
        btc_raw = yf.download("BTC-USD", start="2014-09-01", interval="1d",
                              auto_adjust=True, progress=False)
        if not btc_raw.empty:
            # Extract Close — guard against MultiIndex columns
            if isinstance(btc_raw.columns, pd.MultiIndex):
                btc_close = to_series_1d(btc_raw["Close"])
            else:
                btc_close = to_series_1d(btc_raw[["Close"]])

            btc_m = btc_close.resample("ME").last().dropna()
            btc_m = btc_m.iloc[:-1]   # drop incomplete current month

            if len(btc_m) > 0:
                result["BTC-USD"] = btc_m
                print(f"  BTC-USD: {len(btc_m)} months  "
                      f"({btc_m.index[0].date()} → {btc_m.index[-1].date()})")
            else:
                print("  BTC-USD: resampled to 0 rows — excluding")
        else:
            print("  BTC-USD: no data returned — excluding")

    return result

# ── Backtest ──────────────────────────────────────────────────────────────────
def run_backtest(price_data):
    # Normalise all series to month-start, tz-naive before computing signals
    normalized = {t: normalize_index(p) for t, p in price_data.items()}
    sig_frames = {t: signals(p) for t, p in normalized.items()}

    # Date intersection — limited by the shortest history (BTC from 2014-09)
    all_dates = sorted(set.intersection(*[set(df.index) for df in sig_frames.values()]))
    if not all_dates:
        raise ValueError("No overlapping dates across tickers after normalisation.")
    all_dates = pd.DatetimeIndex(all_dates)
    print(f"\nBacktest range: {all_dates[0].date()} → {all_dates[-1].date()}  "
          f"({len(all_dates)} months)")

    capital         = float(START_CAPITAL)
    holdings        = {}          # {ticker: shares}
    current_tickers = []
    equity_curve    = []
    trade_log       = []

    for date in all_dates:
        # ── Compute signals ───────────────────────────────────────────────────
        buy_signals = [
            t for t in UNIVERSE
            if t in sig_frames
            and date in sig_frames[t].index
            and bool(sig_frames[t].loc[date, "is_buy"])
        ]
        target = buy_signals  # empty list = full cash, no positions

        # ── Rebalance when target changes ─────────────────────────────────────
        if set(target) != set(current_tickers):
            # Sell everything
            proceeds = 0.0
            for ticker, shares in holdings.items():
                if date in sig_frames[ticker].index:
                    price     = float(sig_frames[ticker].loc[date, "close"])
                    proceeds += shares * price * (1 - COMMISSION)
                    trade_log.append({
                        "date": date.strftime("%Y-%m"),
                        "action": "SELL",
                        "ticker": ticker,
                        "price": round(price, 4),
                    })
            if proceeds > 0:
                capital = proceeds
            holdings = {}

            # Compute weights — equal weight, BTC capped at 20%
            # target may be empty → full cash, no positions entered
            n       = len(target)
            weights = {}
            if n > 0:
                if "BTC-USD" in target and n > 1:
                    btc_w   = min(1.0 / n, BTC_CAP)
                    other_w = (1.0 - btc_w) / (n - 1)
                    for t in target:
                        weights[t] = btc_w if t == "BTC-USD" else other_w
                else:
                    for t in target:
                        weights[t] = 1.0 / n

                # Buy
                for ticker in target:
                    if date not in sig_frames[ticker].index:
                        continue
                    price            = float(sig_frames[ticker].loc[date, "close"])
                    alloc            = capital * weights[ticker]
                    shares           = (alloc * (1 - COMMISSION)) / price
                    holdings[ticker] = shares
                    trade_log.append({
                        "date":       date.strftime("%Y-%m"),
                        "action":     "BUY",
                        "ticker":     ticker,
                        "price":      round(price, 4),
                        "weight_pct": round(weights[ticker] * 100, 1),
                    })
            current_tickers = list(target)

        # ── Mark to market ────────────────────────────────────────────────────
        # When in cash (no holdings), port_value = capital unchanged
        if holdings:
            port_value = sum(
                holdings[t] * float(sig_frames[t].loc[date, "close"])
                for t in holdings
                if date in sig_frames[t].index
            )
        else:
            port_value = capital
        equity_curve.append({
            "date":     date.strftime("%Y-%m-%d"),
            "value":    round(port_value, 2),
            "holdings": list(holdings.keys()) if holdings else ["CASH"],
        })

    # ── Performance metrics ───────────────────────────────────────────────────
    values      = pd.Series([e["value"] for e in equity_curve])
    n_months    = len(values)
    n_years     = n_months / 12
    total_ret   = (values.iloc[-1] / START_CAPITAL - 1) * 100
    cagr        = ((values.iloc[-1] / START_CAPITAL) ** (1 / n_years) - 1) * 100
    monthly_ret = values.pct_change().dropna()
    sharpe      = ((monthly_ret.mean() / monthly_ret.std()) * math.sqrt(12)
                   if monthly_ret.std() > 0 else 0.0)
    max_dd      = ((values - values.cummax()) / values.cummax()).min() * 100

    def bench(ticker):
        s = sig_frames[ticker]["close"].reindex(all_dates).dropna()
        ret  = (s.iloc[-1] / s.iloc[0] - 1) * 100
        cagr = ((s.iloc[-1] / s.iloc[0]) ** (1 / n_years) - 1) * 100
        return round(ret, 2), round(cagr, 2)

    spy_ret,  spy_cagr  = bench("SPY")
    btc_ret,  btc_cagr  = bench("BTC-USD")

    holding_counts = {}
    for e in equity_curve:
        for t in e["holdings"]:
            holding_counts[t] = holding_counts.get(t, 0) + 1
    time_in = {t: round(c / n_months * 100, 1)
               for t, c in holding_counts.items()}

    return {
        "summary": {
            "start_date":    all_dates[0].strftime("%Y-%m-%d"),
            "end_date":      all_dates[-1].strftime("%Y-%m-%d"),
            "months":        n_months,
            "start_capital": START_CAPITAL,
            "end_value":     round(float(values.iloc[-1]), 2),
            "total_return":  round(total_ret, 2),
            "cagr":          round(cagr, 2),
            "sharpe":        round(sharpe, 3),
            "max_drawdown":  round(max_dd, 2),
            "n_trades":      len([t for t in trade_log if t["action"] == "SELL"]),
            "spy_return":    spy_ret,
            "spy_cagr":      spy_cagr,
            "btc_return":    btc_ret,
            "btc_cagr":      btc_cagr,
        },
        "time_in_asset": time_in,
        "equity_curve":  equity_curve,
        "trades":        trade_log,
    }

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("DMG Capital — ETF + Bitcoin Rotation Backtest v2")
    print("Signal  : CallingMarkets 2-of-3 on monthly bars")
    print("Universe:", ", ".join(UNIVERSE.keys()))
    print("Cash    : real cash (0%) when no signals  |  BTC cap: 20%  |  Commission: 0.1%")
    print("=" * 65)

    tickers    = list(UNIVERSE.keys())
    price_data = fetch_monthly(tickers)

    missing = [t for t in tickers if t not in price_data]
    if missing:
        print(f"  Warning: no data for {missing}")

    results = run_backtest(price_data)
    s       = results["summary"]

    print(f"\n{'─'*65}")
    print(f"  Period        : {s['start_date']} → {s['end_date']} ({s['months']} months)")
    print(f"  Start capital : ${s['start_capital']:,.0f}")
    print(f"  End value     : ${s['end_value']:,.0f}")
    print(f"  Total return  : {s['total_return']:+.2f}%")
    print(f"  CAGR          : {s['cagr']:+.2f}%")
    print(f"  Sharpe        : {s['sharpe']:.3f}")
    print(f"  Max Drawdown  : {s['max_drawdown']:.2f}%")
    print(f"  Trades        : {s['n_trades']}")
    print(f"\n  Benchmarks (same period):")
    print(f"    SPY B&H     : {s['spy_return']:+.2f}%  ({s['spy_cagr']:+.2f}% CAGR)")
    print(f"    BTC B&H     : {s['btc_return']:+.2f}%  ({s['btc_cagr']:+.2f}% CAGR)")
    print(f"  Alpha vs SPY  : {s['cagr'] - s['spy_cagr']:+.2f}% CAGR")

    print(f"\n  Time allocation:")
    for ticker, pct in sorted(results["time_in_asset"].items(), key=lambda x: -x[1]):
        print(f"    {ticker:<9} {pct:>5.1f}%  {UNIVERSE.get(ticker, '')}")

    # ── JSON output ───────────────────────────────────────────────────────────
    with open("etf_rotation_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n✓ etf_rotation_results.json written")

    # ── Markdown output ───────────────────────────────────────────────────────
    ts  = datetime.now(timezone.utc).strftime("%B %d, %Y")
    md  = f"# ETF + Bitcoin Rotation Backtest — {ts}\n\n"
    md += f"**Signal:** CallingMarkets 2-of-3 (EMA20/55, RSI14>EMA, MACD) on monthly bars  \n"
    md += f"**Universe:** {', '.join(tickers)}  \n"
    md += f"**Weighting:** Equal weight among BUY signals; BTC capped at 20%; BIL when flat\n\n"
    md += f"## Results\n\n"
    md += f"| Metric | Strategy | SPY B&H | BTC B&H |\n"
    md += f"|--------|----------|---------|---------|\n"
    md += f"| Period | {s['start_date']} → {s['end_date']} | — | — |\n"
    md += f"| Total Return | {s['total_return']:+.2f}% | {s['spy_return']:+.2f}% | {s['btc_return']:+.2f}% |\n"
    md += f"| CAGR | {s['cagr']:+.2f}% | {s['spy_cagr']:+.2f}% | {s['btc_cagr']:+.2f}% |\n"
    md += f"| Sharpe | {s['sharpe']:.3f} | — | — |\n"
    md += f"| Max Drawdown | {s['max_drawdown']:.2f}% | — | — |\n"
    md += f"| End Value ($100k start) | ${s['end_value']:,.0f} | — | — |\n"
    md += f"| Trades | {s['n_trades']} | — | — |\n\n"
    md += f"## Time Allocation\n\n"
    md += f"| Asset | % Time | Description |\n|-------|--------|-------------|\n"
    for ticker, pct in sorted(results["time_in_asset"].items(), key=lambda x: -x[1]):
        md += f"| {ticker} | {pct}% | {UNIVERSE.get(ticker, '')} |\n"
    md += (f"\n---\n*BTC-USD data from Sep 2014. Universe: SPY, QQQ, IWM, EEM, TLT, SHY, GLD, DJP, BTC-USD. "
           f"Cash: real cash (0%) when no signals fire. Commission: {COMMISSION*100:.1f}% per trade. BTC capped at {int(BTC_CAP*100)}%.*\n")

    with open("etf_rotation_results.md", "w") as f:
        f.write(md)
    print("✓ etf_rotation_results.md written")


if __name__ == "__main__":
    main()

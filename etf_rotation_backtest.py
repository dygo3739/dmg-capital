#!/usr/bin/env python3
"""
DMG Capital — ETF Rotation Backtest
Signal: CallingMarkets 2-of-3 (EMA20>EMA55, RSI14>EMA14, MACD>Signal) on monthly bars
Universe: 9-asset macro rotation basket including Bitcoin
Weighting: Equal weight among BUY signals; BTC capped at 20%; BIL (cash) when no signals
Data: yfinance — ETFs via monthly interval, BTC-USD via daily resampled to monthly
Outputs: etf_rotation_results.json, etf_rotation_results.md
"""

import json, math
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# ── Universe ──────────────────────────────────────────────────────────────────
UNIVERSE = {
    "SPY":     "US Large Cap (S&P 500)",
    "QQQ":     "US Tech / Nasdaq 100",
    "EEM":     "Emerging Markets",
    "TLT":     "Long-Term Treasuries (20yr+)",
    "GLD":     "Gold",
    "DJP":     "Broad Commodities",
    "VNQ":     "US Real Estate (REIT)",
    "BIL":     "Short-Term Bills (Cash proxy)",
    "BTC-USD": "Bitcoin",
}

CASH    = "BIL"
BTC_CAP = 0.20          # Bitcoin capped at 20% regardless of signal strength
COMMISSION   = 0.001    # 0.1% per trade
START_CAPITAL = 100_000

# ── Indicators (mirrors Pine Script exactly) ──────────────────────────────────
def calc_ema(s, n):  return s.ewm(span=n, adjust=False).mean()
def calc_rma(s, n):  return s.ewm(alpha=1/n, adjust=False).mean()

def calc_rsi(s, n=14):
    d    = s.diff()
    gain = calc_rma(d.clip(lower=0), n)
    loss = calc_rma((-d).clip(lower=0), n)
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))

def signals(close):
    close = close.squeeze().astype(float)   # ensure 1D Series — handles DataFrame column input
    ema20     = calc_ema(close, 20)
    ema55     = calc_ema(close, 55)
    rsi14     = calc_rsi(close, 14)
    rsi_ma    = calc_ema(rsi14, 14)
    macd      = calc_ema(close, 12) - calc_ema(close, 26)
    sig_line  = calc_ema(macd, 9)

    bull1  = ema20 > ema55
    bull2  = rsi14 > rsi_ma
    bull3  = macd  > sig_line
    score  = bull1.astype(int) + bull2.astype(int) + bull3.astype(int)
    is_buy = score >= 2

    return pd.DataFrame({
        "close":  close,
        "bull1":  bull1,
        "bull2":  bull2,
        "bull3":  bull3,
        "score":  score,
        "is_buy": is_buy,
    }, index=close.index)

# ── Data fetch ────────────────────────────────────────────────────────────────
def fetch_monthly(tickers, start="2003-01-01"):
    result = {}
    etf_tickers = [t for t in tickers if t != "BTC-USD"]

    # ── ETFs via monthly interval ─────────────────────────────────────────────
    print(f"Fetching ETF monthly data: {etf_tickers}")
    raw = yf.download(etf_tickers, start=start, interval="1mo",
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw[["Close"]].rename(columns={"Close": etf_tickers[0]})
    closes = closes.iloc[:-1]   # drop incomplete current month
    print(f"  ETFs: {len(closes)} months  ({closes.index[0].date()} → {closes.index[-1].date()})")
    for t in etf_tickers:
        if t in closes.columns:
            result[t] = closes[t].dropna().squeeze()

    # ── BTC-USD via daily → resample to monthly ───────────────────────────────
    if "BTC-USD" in tickers:
        print("Fetching BTC-USD daily data (resampling to monthly)...")
        btc = yf.download("BTC-USD", start="2014-09-01", interval="1d",
                          auto_adjust=True, progress=False)
        if not btc.empty:
            col       = "Close" if "Close" in btc.columns else btc.columns[0]
            btc_m     = btc[col].resample("ME").last().dropna()
            btc_m     = btc_m.iloc[:-1]   # drop incomplete current month
            # Squeeze to 1D Series if yfinance returned a DataFrame
            if isinstance(btc_m, pd.DataFrame):
                btc_m = btc_m.iloc[:, 0]
            btc_m.index = btc_m.index.tz_localize(None)  # strip UTC tz to match ETF index
            result["BTC-USD"] = btc_m
            print(f"  BTC-USD: {len(btc_m)} months  ({btc_m.index[0].date()} → {btc_m.index[-1].date()})")
        else:
            print("  BTC-USD: no data returned — excluding from backtest")

    return result

# ── Backtest ──────────────────────────────────────────────────────────────────
def run_backtest(price_data):
    # Normalize all series to month-start frequency before computing signals
    # ETFs arrive as month-start, BTC arrives as month-end — must align to same anchor
    normalized = {}
    for ticker, prices in price_data.items():
        s = prices.copy()
        s.index = s.index.to_period("M").to_timestamp("MS")   # snap to month-start
        s = s[~s.index.duplicated(keep="last")]                # drop any dupes
        normalized[ticker] = s

    sig_frames = {ticker: signals(prices) for ticker, prices in normalized.items()}

    # Date range — intersection of all tickers that have data
    # BTC only has data from 2014-09, so intersection starts there
    all_dates = sorted(set.intersection(*[set(df.index) for df in sig_frames.values()]))
    all_dates = pd.DatetimeIndex(all_dates)
    print(f"\nBacktest range: {all_dates[0].date()} → {all_dates[-1].date()}  ({len(all_dates)} months)")
    print("Note: range starts at BTC-USD data availability (2014-09)")

    capital         = float(START_CAPITAL)
    holdings        = {}
    current_tickers = []
    equity_curve    = []
    trade_log       = []

    for date in all_dates:
        # ── Signals at month-end ──────────────────────────────────────────────
        buy_signals = []
        for ticker in UNIVERSE:
            df = sig_frames.get(ticker)
            if df is None or date not in df.index:
                continue
            if df.loc[date, "is_buy"]:
                buy_signals.append(ticker)

        target = buy_signals if buy_signals else [CASH]

        # ── Rebalance on change ───────────────────────────────────────────────
        if set(target) != set(current_tickers):
            # Liquidate
            proceeds = 0.0
            for ticker, shares in holdings.items():
                price     = float(sig_frames[ticker].loc[date, "close"])
                proceeds += shares * price * (1 - COMMISSION)
                trade_log.append({"date": date.strftime("%Y-%m"), "action": "SELL",
                                  "ticker": ticker, "price": round(price, 4)})
            capital  = proceeds if proceeds > 0 else capital
            holdings = {}

            # Weights: equal weight with BTC capped at 20%
            n = len(target)
            weights = {}
            if "BTC-USD" in target and n > 1:
                base    = 1.0 / n
                btc_w   = min(base, BTC_CAP)
                other_w = (1.0 - btc_w) / (n - 1)
                for t in target:
                    weights[t] = btc_w if t == "BTC-USD" else other_w
            else:
                for t in target:
                    weights[t] = 1.0 / n

            # Buy
            for ticker in target:
                price            = float(sig_frames[ticker].loc[date, "close"])
                alloc            = capital * weights[ticker]
                shares           = (alloc * (1 - COMMISSION)) / price
                holdings[ticker] = shares
                trade_log.append({"date": date.strftime("%Y-%m"), "action": "BUY",
                                  "ticker": ticker, "price": round(price, 4),
                                  "weight_pct": round(weights[ticker] * 100, 1)})
            current_tickers = list(target)

        # ── Mark to market ────────────────────────────────────────────────────
        port_value = sum(
            holdings[t] * float(sig_frames[t].loc[date, "close"])
            for t in holdings if date in sig_frames[t].index
        )
        equity_curve.append({
            "date":     date.strftime("%Y-%m-%d"),
            "value":    round(port_value, 2),
            "holdings": list(holdings.keys()),
        })

    # ── Metrics ───────────────────────────────────────────────────────────────
    values      = pd.Series([e["value"] for e in equity_curve])
    n_months    = len(values)
    n_years     = n_months / 12
    total_ret   = (values.iloc[-1] / START_CAPITAL - 1) * 100
    cagr        = ((values.iloc[-1] / START_CAPITAL) ** (1 / n_years) - 1) * 100
    monthly_ret = values.pct_change().dropna()
    sharpe      = (monthly_ret.mean() / monthly_ret.std()) * math.sqrt(12) if monthly_ret.std() > 0 else 0
    max_dd      = ((values - values.cummax()) / values.cummax()).min() * 100

    # SPY benchmark over same period
    spy_s    = pd.Series([float(sig_frames["SPY"].loc[d, "close"]) for d in all_dates if d in sig_frames["SPY"].index])
    spy_ret  = (spy_s.iloc[-1] / spy_s.iloc[0] - 1) * 100
    spy_cagr = ((spy_s.iloc[-1] / spy_s.iloc[0]) ** (1 / n_years) - 1) * 100

    # BTC benchmark over same period
    btc_s    = pd.Series([float(sig_frames["BTC-USD"].loc[d, "close"]) for d in all_dates if d in sig_frames["BTC-USD"].index])
    btc_ret  = (btc_s.iloc[-1] / btc_s.iloc[0] - 1) * 100
    btc_cagr = ((btc_s.iloc[-1] / btc_s.iloc[0]) ** (1 / n_years) - 1) * 100

    # Time in each asset
    holding_counts = {}
    for e in equity_curve:
        for t in e["holdings"]:
            holding_counts[t] = holding_counts.get(t, 0) + 1
    time_in = {t: round(c / n_months * 100, 1) for t, c in holding_counts.items()}

    return {
        "summary": {
            "start_date":    all_dates[0].strftime("%Y-%m-%d"),
            "end_date":      all_dates[-1].strftime("%Y-%m-%d"),
            "months":        n_months,
            "start_capital": START_CAPITAL,
            "end_value":     round(values.iloc[-1], 2),
            "total_return":  round(total_ret, 2),
            "cagr":          round(cagr, 2),
            "sharpe":        round(sharpe, 3),
            "max_drawdown":  round(max_dd, 2),
            "n_trades":      len([t for t in trade_log if t["action"] == "SELL"]),
            "spy_return":    round(spy_ret, 2),
            "spy_cagr":      round(spy_cagr, 2),
            "btc_return":    round(btc_ret, 2),
            "btc_cagr":      round(btc_cagr, 2),
        },
        "time_in_asset": time_in,
        "equity_curve":  equity_curve,
        "trades":        trade_log,
    }

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("DMG Capital — ETF Rotation Backtest (with Bitcoin)")
    print("Signal: CallingMarkets 2-of-3 on monthly bars")
    print("BTC-USD capped at 20% allocation")
    print("=" * 65)

    tickers    = list(UNIVERSE.keys())
    price_data = fetch_monthly(tickers)

    missing = [t for t in tickers if t not in price_data]
    if missing:
        print(f"  Warning: no data for {missing}")

    results = run_backtest(price_data)
    s       = results["summary"]

    print(f"\n{'─'*65}")
    print(f"  Period:        {s['start_date']} → {s['end_date']} ({s['months']} months)")
    print(f"  Start capital: ${s['start_capital']:,.0f}")
    print(f"  End value:     ${s['end_value']:,.0f}")
    print(f"  Total return:  {s['total_return']:+.2f}%")
    print(f"  CAGR:          {s['cagr']:+.2f}%")
    print(f"  Sharpe:        {s['sharpe']:.3f}")
    print(f"  Max Drawdown:  {s['max_drawdown']:.2f}%")
    print(f"  Trades:        {s['n_trades']}")
    print(f"\n  Benchmarks (same period):")
    print(f"    SPY B&H:     {s['spy_return']:+.2f}%  ({s['spy_cagr']:+.2f}% CAGR)")
    print(f"    BTC B&H:     {s['btc_return']:+.2f}%  ({s['btc_cagr']:+.2f}% CAGR)")
    print(f"  Alpha vs SPY:  {s['cagr'] - s['spy_cagr']:+.2f}% CAGR")

    print(f"\n  Time allocation:")
    for ticker, pct in sorted(results["time_in_asset"].items(), key=lambda x: -x[1]):
        label = UNIVERSE.get(ticker, ticker)
        print(f"    {ticker:<9} {pct:>5.1f}%  {label}")

    # ── Save JSON ──────────────────────────────────────────────────────────────
    with open("etf_rotation_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n✓ etf_rotation_results.json written")

    # ── Save markdown ──────────────────────────────────────────────────────────
    ts   = datetime.now(timezone.utc).strftime("%B %d, %Y")
    md   = f"# ETF + Bitcoin Rotation Backtest — {ts}\n\n"
    md  += f"**Signal:** CallingMarkets 2-of-3 momentum (EMA20/55, RSI14>EMA, MACD) on monthly bars  \n"
    md  += f"**Universe:** {', '.join(tickers)}  \n"
    md  += f"**Weighting:** Equal weight among BUY signals; BTC capped at 20%; BIL when no signals\n\n"
    md  += f"## Results\n\n"
    md  += f"| Metric | Strategy | SPY B&H | BTC B&H |\n"
    md  += f"|--------|----------|---------|----------|\n"
    md  += f"| Period | {s['start_date']} → {s['end_date']} | — | — |\n"
    md  += f"| Total Return | {s['total_return']:+.2f}% | {s['spy_return']:+.2f}% | {s['btc_return']:+.2f}% |\n"
    md  += f"| CAGR | {s['cagr']:+.2f}% | {s['spy_cagr']:+.2f}% | {s['btc_cagr']:+.2f}% |\n"
    md  += f"| Sharpe | {s['sharpe']:.3f} | — | — |\n"
    md  += f"| Max Drawdown | {s['max_drawdown']:.2f}% | — | — |\n"
    md  += f"| End Value ($100k) | ${s['end_value']:,.0f} | — | — |\n"
    md  += f"| Trades | {s['n_trades']} | — | — |\n\n"
    md  += f"## Time Allocation\n\n| Asset | % Time | Description |\n|-------|--------|-------------|\n"
    for ticker, pct in sorted(results["time_in_asset"].items(), key=lambda x: -x[1]):
        md += f"| {ticker} | {pct}% | {UNIVERSE.get(ticker, '')} |\n"
    md  += f"\n---\n*BTC-USD data from 2014-09. Commission: {COMMISSION*100:.1f}% per trade. BTC capped at 20%.*\n"

    with open("etf_rotation_results.md", "w") as f:
        f.write(md)
    print(f"✓ etf_rotation_results.md written")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
DMG Capital — ETF Rotation Backtest
Signal: CallingMarkets 2-of-3 (EMA20>EMA55, RSI14>EMA14, MACD>Signal) on monthly bars
Universe: 8-ETF macro rotation basket
Weighting: Equal weight among BUY signals; 100% BIL (cash) when no signals
Data: yfinance monthly OHLC
Outputs: etf_rotation_results.json, etf_rotation_results.md
"""

import json, math
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# ── Universe ──────────────────────────────────────────────────────────────────
UNIVERSE = {
    "SPY":  "US Large Cap (S&P 500)",
    "QQQ":  "US Tech / Nasdaq 100",
    "EEM":  "Emerging Markets",
    "TLT":  "Long-Term Treasuries (20yr+)",
    "GLD":  "Gold",
    "DJP":  "Broad Commodities",
    "VNQ":  "US Real Estate (REIT)",
    "BIL":  "Short-Term Bills (Cash proxy)",
}

# BIL is our cash proxy — always in the eligible set but treated as default
CASH = "BIL"

START_CAPITAL = 100_000
COMMISSION    = 0.001   # 0.1% per trade (ETFs, not crypto)

# ── Indicators (mirrors Pine Script exactly) ──────────────────────────────────
def calc_ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def calc_rma(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1/n, adjust=False).mean()

def calc_rsi(s: pd.Series, n: int = 14) -> pd.Series:
    delta = s.diff()
    gain  = calc_rma(delta.clip(lower=0), n)
    loss  = calc_rma((-delta).clip(lower=0), n)
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))

def calc_macd(s: pd.Series, fast=12, slow=26, sig=9):
    macd_line = calc_ema(s, fast) - calc_ema(s, slow)
    sig_line  = calc_ema(macd_line, sig)
    return macd_line, sig_line

def signals(close: pd.Series) -> pd.DataFrame:
    """Return per-bar signal DataFrame for one ticker."""
    ema20     = calc_ema(close, 20)
    ema55     = calc_ema(close, 55)
    rsi14     = calc_rsi(close, 14)
    rsi_ma    = calc_ema(rsi14, 14)
    macd, sig = calc_macd(close)

    bull1 = ema20 > ema55
    bull2 = rsi14 > rsi_ma
    bull3 = macd  > sig

    score  = bull1.astype(int) + bull2.astype(int) + bull3.astype(int)
    is_buy = score >= 2

    return pd.DataFrame({
        "close":  close,
        "bull1":  bull1,
        "bull2":  bull2,
        "bull3":  bull3,
        "score":  score,
        "is_buy": is_buy,
    })

# ── Data fetch ────────────────────────────────────────────────────────────────
def fetch_monthly(tickers: list[str], start="2003-01-01") -> dict[str, pd.Series]:
    """Download monthly close prices via yfinance."""
    print(f"Fetching monthly data for {tickers}...")
    raw = yf.download(tickers, start=start, interval="1mo", auto_adjust=True, progress=False)

    # yfinance returns MultiIndex when multiple tickers
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw[["Close"]].rename(columns={"Close": tickers[0]})

    # Drop incomplete current month
    closes = closes.iloc[:-1]
    print(f"  Got {len(closes)} monthly bars ({closes.index[0].date()} → {closes.index[-1].date()})")
    return {t: closes[t].dropna() for t in tickers if t in closes.columns}

# ── Backtest ──────────────────────────────────────────────────────────────────
def run_backtest(price_data: dict[str, pd.Series]) -> dict:
    """
    Monthly rotation backtest.
    On each month-end bar: compute signals → equal weight BUY signals.
    If nothing is BUY, go to BIL (cash).
    Execute at next month's open (approximated as next month's close for simplicity).
    """
    # Build signal table for every ticker
    sig_frames = {}
    for ticker, prices in price_data.items():
        sig_frames[ticker] = signals(prices)

    # Common date index — months where all tickers have data
    all_dates = sorted(set.intersection(*[set(df.index) for df in sig_frames.values()]))
    all_dates = pd.DatetimeIndex(all_dates)

    print(f"\nBacktest date range: {all_dates[0].date()} → {all_dates[-1].date()} ({len(all_dates)} months)")

    # Portfolio state
    capital     = float(START_CAPITAL)
    holdings    = {}   # {ticker: shares}
    equity_curve = []
    trade_log    = []
    current_tickers = []

    for i, date in enumerate(all_dates):
        # ── Compute signals at month-end ──
        buy_signals = []
        for ticker in UNIVERSE:
            df = sig_frames.get(ticker)
            if df is None or date not in df.index:
                continue
            row = df.loc[date]
            if row["is_buy"]:
                buy_signals.append(ticker)

        # Default to cash if nothing is BUY
        if not buy_signals:
            target = [CASH]
        else:
            target = buy_signals

        # ── Rebalance if holdings changed ──
        if set(target) != set(current_tickers):
            # Liquidate current holdings
            proceeds = 0.0
            for ticker, shares in holdings.items():
                price = float(sig_frames[ticker].loc[date, "close"])
                proceeds += shares * price * (1 - COMMISSION)
                trade_log.append({
                    "date":   date.strftime("%Y-%m"),
                    "action": "SELL",
                    "ticker": ticker,
                    "price":  round(price, 4),
                    "shares": round(shares, 4),
                })
            capital  = proceeds if proceeds > 0 else capital
            holdings = {}

            # Buy new targets equally weighted
            alloc = capital / len(target)
            for ticker in target:
                price  = float(sig_frames[ticker].loc[date, "close"])
                shares = (alloc * (1 - COMMISSION)) / price
                holdings[ticker] = shares
                trade_log.append({
                    "date":   date.strftime("%Y-%m"),
                    "action": "BUY",
                    "ticker": ticker,
                    "price":  round(price, 4),
                    "shares": round(shares, 4),
                })
            current_tickers = list(target)

        # ── Mark to market ──
        port_value = sum(
            holdings[t] * float(sig_frames[t].loc[date, "close"])
            for t in holdings if date in sig_frames[t].index
        )
        equity_curve.append({"date": date.strftime("%Y-%m-%d"), "value": round(port_value, 2), "holdings": list(holdings.keys())})

    # ── Performance metrics ───────────────────────────────────────────────────
    values   = pd.Series([e["value"] for e in equity_curve])
    n_months = len(values)
    n_years  = n_months / 12

    total_return = (values.iloc[-1] / START_CAPITAL - 1) * 100
    cagr         = ((values.iloc[-1] / START_CAPITAL) ** (1 / n_years) - 1) * 100

    monthly_ret  = values.pct_change().dropna()
    sharpe       = (monthly_ret.mean() / monthly_ret.std()) * math.sqrt(12) if monthly_ret.std() > 0 else 0

    roll_max     = values.cummax()
    drawdown     = (values - roll_max) / roll_max
    max_dd       = drawdown.min() * 100

    # SPY buy-and-hold benchmark
    spy_prices   = pd.Series([
        float(sig_frames["SPY"].loc[d, "close"])
        for d in all_dates if d in sig_frames["SPY"].index
    ])
    spy_return   = (spy_prices.iloc[-1] / spy_prices.iloc[0] - 1) * 100
    spy_cagr     = ((spy_prices.iloc[-1] / spy_prices.iloc[0]) ** (1 / n_years) - 1) * 100

    # Trade stats
    sells   = [t for t in trade_log if t["action"] == "SELL"]
    n_trades = len(sells)

    # Time in each asset
    holding_counts = {}
    for e in equity_curve:
        for t in e["holdings"]:
            holding_counts[t] = holding_counts.get(t, 0) + 1
    time_in = {t: round(c / n_months * 100, 1) for t, c in holding_counts.items()}

    return {
        "summary": {
            "start_date":     all_dates[0].strftime("%Y-%m-%d"),
            "end_date":       all_dates[-1].strftime("%Y-%m-%d"),
            "months":         n_months,
            "start_capital":  START_CAPITAL,
            "end_value":      round(values.iloc[-1], 2),
            "total_return":   round(total_return, 2),
            "cagr":           round(cagr, 2),
            "sharpe":         round(sharpe, 3),
            "max_drawdown":   round(max_dd, 2),
            "n_trades":       n_trades,
            "spy_return":     round(spy_return, 2),
            "spy_cagr":       round(spy_cagr, 2),
        },
        "time_in_asset":  time_in,
        "equity_curve":   equity_curve,
        "trades":         trade_log,
    }

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("DMG Capital — ETF Rotation Backtest")
    print("Signal: CallingMarkets 2-of-3 (EMA20/55, RSI14>EMA, MACD) on monthly bars")
    print("="*65)

    tickers    = list(UNIVERSE.keys())
    price_data = fetch_monthly(tickers)

    missing = [t for t in tickers if t not in price_data]
    if missing:
        print(f"  Warning: no data for {missing}")

    results = run_backtest(price_data)
    s = results["summary"]

    print(f"\n{'─'*65}")
    print(f"  Backtest:      {s['start_date']} → {s['end_date']} ({s['months']} months)")
    print(f"  Start capital: ${s['start_capital']:,.0f}")
    print(f"  End value:     ${s['end_value']:,.0f}")
    print(f"  Total return:  {s['total_return']:+.2f}%")
    print(f"  CAGR:          {s['cagr']:+.2f}%")
    print(f"  Sharpe:        {s['sharpe']:.3f}")
    print(f"  Max Drawdown:  {s['max_drawdown']:.2f}%")
    print(f"  Trades:        {s['n_trades']}")
    print(f"\n  SPY B&H:       {s['spy_return']:+.2f}%  ({s['spy_cagr']:+.2f}% CAGR)")
    print(f"  Alpha vs SPY:  {s['cagr'] - s['spy_cagr']:+.2f}% CAGR")

    print(f"\n  Time allocation:")
    for ticker, pct in sorted(results["time_in_asset"].items(), key=lambda x: -x[1]):
        label = UNIVERSE.get(ticker, ticker)
        print(f"    {ticker:<5} {pct:>5.1f}%  {label}")

    # Save JSON
    with open("etf_rotation_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n✓ etf_rotation_results.json written")

    # Save markdown
    ts  = datetime.now(timezone.utc).strftime("%B %d, %Y")
    md  = f"# ETF Rotation Backtest — {ts}\n\n"
    md += f"**Signal:** CallingMarkets 2-of-3 momentum on monthly bars\n"
    md += f"**Universe:** {', '.join(tickers)}\n"
    md += f"**Weighting:** Equal weight among BUY signals; BIL (cash) when none\n\n"
    md += f"## Results\n\n"
    md += f"| Metric | Strategy | SPY B&H |\n|--------|----------|----------|\n"
    md += f"| Period | {s['start_date']} → {s['end_date']} | — |\n"
    md += f"| Total Return | {s['total_return']:+.2f}% | {s['spy_return']:+.2f}% |\n"
    md += f"| CAGR | {s['cagr']:+.2f}% | {s['spy_cagr']:+.2f}% |\n"
    md += f"| Sharpe | {s['sharpe']:.3f} | — |\n"
    md += f"| Max Drawdown | {s['max_drawdown']:.2f}% | — |\n"
    md += f"| End Value ($100k start) | ${s['end_value']:,.0f} | — |\n"
    md += f"| Trades | {s['n_trades']} | — |\n\n"
    md += f"## Time Allocation\n\n| ETF | % Time | Description |\n|-----|--------|-------------|\n"
    for ticker, pct in sorted(results["time_in_asset"].items(), key=lambda x: -x[1]):
        md += f"| {ticker} | {pct}% | {UNIVERSE.get(ticker, '')} |\n"
    md += f"\n---\n*Signal recomputed monthly. Commission: {COMMISSION*100:.1f}% per trade.*\n"

    with open("etf_rotation_results.md", "w") as f:
        f.write(md)
    print(f"✓ etf_rotation_results.md written")

if __name__ == "__main__":
    main()

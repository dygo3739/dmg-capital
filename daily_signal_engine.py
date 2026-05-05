#!/usr/bin/env python3
"""
DMG Capital — Daily Strategy Engine (Test Build)
- Same universe and BTC gate logic as the weekly strategy
- Uses DAILY bars (interval=1440) instead of weekly
- Adapted indicators: EMA10>EMA30, RSI10>EMA10, MACD(6,13,4) — scaled for daily
- Runs daily, generates signals + equity curve for fast live testing
- Outputs: portfolios_daily.json, trade_history_daily.json
"""

import json, time
from datetime import datetime, timezone
import requests
import pandas as pd
import numpy as np

STARTING_CAPITAL = 1_000.0          # Small — for live testing with real money
KRAKEN_BASE      = "https://api.kraken.com/0/public"
PORTFOLIO_ID     = "crypto-rotation-daily"
TAKER_FEE        = 0.0026

# ── Universe — same as weekly strategy ───────────────────────────────────────
UNIVERSE_BY_YEAR = {
    2018: ["BTC","ETH","XRP","BCH","ADA","LTC","XMR","ETC","ZEC","DASH"],
    2019: ["BTC","ETH","XRP","LTC","BCH","XLM","ADA","TRX","XMR","DOGE"],
    2020: ["BTC","ETH","XRP","BCH","LTC","XLM","ADA","LINK","TRX","XMR"],
    2021: ["BTC","ETH","XRP","ADA","LTC","DOT","LINK","DOGE","BCH","UNI"],
    2022: ["BTC","ETH","SOL","ADA","XRP","DOT","DOGE","AVAX","LTC","TRX"],
    2023: ["BTC","ETH","XRP","DOGE","ADA","SOL","LTC","TRX","AVAX","LINK"],
    2024: ["BTC","ETH","SOL","XRP","ADA","AVAX","DOGE","TRX","LINK","LTC"],
    2025: ["BTC","ETH","XRP","SOL","DOGE","ADA","TRX","AVAX","LINK","BCH"],
}

KRAKEN_PAIRS = {
    "BTC":"XBTUSD","ETH":"ETHUSD","XRP":"XRPUSD","LTC":"LTCUSD",
    "BCH":"BCHUSD","ADA":"ADAUSD","DOT":"DOTUSD","LINK":"LINKUSD",
    "XLM":"XLMUSD","DOGE":"XDGUSD","SOL":"SOLUSD","AVAX":"AVAXUSD",
    "TRX":"TRXUSD","XMR":"XMRUSD","ZEC":"ZECUSD","ETC":"ETCUSD",
    "ATOM":"ATOMUSD","UNI":"UNIUSD","DASH":"DASHUSD","PAXG":"PAXGUSD",
}

ALL_TICKERS = sorted(set(
    t for yr in UNIVERSE_BY_YEAR.values() for t in yr
) | {"PAXG"})

# ── Daily-scaled indicators ───────────────────────────────────────────────────
# Weekly uses EMA20/55, RSI14/14, MACD12/26/9
# Daily equivalent: roughly divide periods by 5 (5 trading days per week)
# EMA10/30 ≈ weekly EMA2/6 — too short, use EMA20/55 directly on daily too
# This gives more signals but similar trend-following character
EMA_FAST  = 20    # ~4 trading weeks
EMA_SLOW  = 55    # ~11 trading weeks
RSI_N     = 14    # 14 days
RSI_EMA   = 14    # EMA of RSI
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIG  = 9

def calc_ema(s, n): return s.ewm(span=n, adjust=False).mean()
def calc_rma(s, n): return s.ewm(alpha=1/n, adjust=False).mean()

def calc_rsi(s, n=14):
    d  = s.diff()
    ag = calc_rma(d.clip(lower=0), n)
    al = calc_rma((-d).clip(lower=0), n)
    return 100 - 100 / (1 + ag / al.replace(0, np.nan))

def compute_signal_daily(daily_close):
    """2-of-3 daily momentum — same logic as weekly, applied to daily bars."""
    if len(daily_close) < 60:
        return None
    ema_fast = calc_ema(daily_close, EMA_FAST)
    ema_slow = calc_ema(daily_close, EMA_SLOW)
    rsi      = calc_rsi(daily_close, RSI_N)
    rsi_ema  = calc_ema(rsi, RSI_EMA)
    macd     = calc_ema(daily_close, MACD_FAST) - calc_ema(daily_close, MACD_SLOW)
    sig_line = calc_ema(macd, MACD_SIG)
    score = ((ema_fast > ema_slow).astype(int) +
             (rsi > rsi_ema).astype(int) +
             (macd > sig_line).astype(int))
    return score.apply(lambda s: "BUY" if s >= 2 else "SELL")

# ── Fetch daily OHLC from Kraken ──────────────────────────────────────────────
def fetch_daily(ticker, since_days=2400):
    pair = KRAKEN_PAIRS.get(ticker)
    if not pair: return None
    since = int(time.time()) - since_days * 86400
    try:
        r = requests.get(
            f"{KRAKEN_BASE}/OHLC",
            params={"pair": pair, "interval": 1440, "since": since},
            timeout=30
        )
        if r.status_code != 200: return None
        data = r.json()
        if data.get("error"): return None
        result = data.get("result", {})
        key = [k for k in result if k != "last"]
        if not key: return None
        bars = result[key[0]]
        if not bars: return None
        df = pd.DataFrame(bars, columns=["time","open","high","low","close","vwap","volume","count"])
        df["date"]  = pd.to_datetime(df["time"].astype(int), unit="s", utc=True)
        df["close"] = df["close"].astype(float)
        df = df.drop_duplicates("date").set_index("date").sort_index()
        daily = df["close"].dropna()
        return daily if len(daily) >= 60 else None
    except Exception as e:
        print(f"  Error {ticker}: {e}")
        return None

def fetch_all_daily():
    price_data = {}
    print(f"\nFetching {len(ALL_TICKERS)} tickers (daily bars)...")
    for i, ticker in enumerate(ALL_TICKERS):
        series = fetch_daily(ticker)
        if series is not None:
            price_data[ticker] = series
            print(f"  {ticker:6s}: {len(series):3d} days "
                  f"({series.index[0].strftime('%Y-%m-%d')} → {series.index[-1].strftime('%Y-%m-%d')})")
        else:
            print(f"  {ticker:6s}: ✗ insufficient data")
        if (i+1) % 5 == 0: time.sleep(0.3)
    return price_data

# ── Universe helper ───────────────────────────────────────────────────────────
def get_universe(date):
    year = date.year
    available = [y for y in sorted(UNIVERSE_BY_YEAR.keys()) if y <= year]
    return UNIVERSE_BY_YEAR[available[-1]] if available else []

# ── Backtest on daily data ────────────────────────────────────────────────────
def run_backtest(price_data):
    signals = {}
    for ticker, prices in price_data.items():
        sig = compute_signal_daily(prices)
        if sig is not None:
            signals[ticker] = sig

    # Backtest from 2019-01-01
    start     = pd.Timestamp("2019-01-01", tz="UTC")
    end       = pd.Timestamp.now(tz="UTC").normalize()
    all_days  = pd.date_range(start, end, freq="D")

    holdings     = {}
    cash         = STARTING_CAPITAL
    equity_curve = []
    trades       = []
    daily_rets   = []
    prev_val     = STARTING_CAPITAL

    # BTC B&H reference
    btc_start    = None
    btc_eq_curve = []

    for date in all_days:
        universe = get_universe(date)

        prices_now = {}
        for t in list(universe) + ["PAXG"]:
            if t in price_data:
                mask = price_data[t].index <= date
                if mask.any():
                    prices_now[t] = float(price_data[t][mask].iloc[-1])

        stock_val = sum(holdings.get(t,0)*prices_now.get(t,0) for t in holdings)
        port_val  = cash + stock_val
        daily_rets.append((port_val/prev_val)-1 if prev_val > 0 else 0)
        prev_val  = port_val

        # BTC B&H tracking
        if "BTC" in prices_now:
            if btc_start is None:
                btc_start = prices_now["BTC"]
            btc_val = STARTING_CAPITAL * (prices_now["BTC"] / btc_start)
            btc_eq_curve.append({"date": date.strftime("%Y-%m-%d"), "value": round(btc_val, 2)})

        # ── BTC gate ──────────────────────────────────────────────────────────
        btc_signal = "SELL"
        if "BTC" in signals:
            mask = signals["BTC"].index <= date
            if mask.any():
                btc_signal = signals["BTC"][mask].iloc[-1]

        paxg_signal = "SELL"
        if "PAXG" in signals:
            mask = signals["PAXG"].index <= date
            if mask.any():
                paxg_signal = signals["PAXG"][mask].iloc[-1]

        # ── Target allocation ─────────────────────────────────────────────────
        if btc_signal == "BUY":
            target_assets = [
                t for t in universe
                if t in signals and signals[t].index[signals[t].index <= date].any()
                and signals[t][signals[t].index <= date].iloc[-1] == "BUY"
                and t != "PAXG"
            ]
        elif paxg_signal == "BUY":
            target_assets = ["PAXG"]
        else:
            target_assets = []

        if not target_assets:
            # Move to cash
            for t in list(holdings.keys()):
                if t in prices_now and holdings.get(t,0) > 0:
                    proceeds = holdings[t] * prices_now[t]
                    fee = proceeds * TAKER_FEE
                    cash += proceeds - fee
                    trades.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "action": "SELL", "ticker": t,
                        "value": round(proceeds, 2), "fee": round(fee, 2),
                        "reason": "Gate SELL or no signals",
                    })
                    del holdings[t]
            equity_curve.append({"date": date.strftime("%Y-%m-%d"), "value": round(cash, 2)})
            continue

        # ── Rebalance ─────────────────────────────────────────────────────────
        n = len(target_assets)
        target_usd = port_val / n

        # Sell assets no longer in target
        for t in list(holdings.keys()):
            if t not in target_assets and t in prices_now and holdings.get(t,0) > 0:
                proceeds = holdings[t] * prices_now[t]
                fee = proceeds * TAKER_FEE
                cash += proceeds - fee
                trades.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "action": "SELL", "ticker": t,
                    "value": round(proceeds, 2), "fee": round(fee, 2),
                    "reason": "Signal → SELL",
                })
                del holdings[t]

        # Buy/rebalance assets in target
        for t in target_assets:
            if t not in prices_now: continue
            price = prices_now[t]
            current_val = holdings.get(t, 0) * price
            drift = abs(current_val - target_usd) / port_val

            if drift > 0.03 or t not in holdings:
                diff = target_usd - current_val
                if diff > 10:  # Buy
                    fee = diff * TAKER_FEE
                    qty = (diff - fee) / price
                    if cash >= diff:
                        cash -= diff
                        holdings[t] = holdings.get(t, 0) + qty
                        trades.append({
                            "date": date.strftime("%Y-%m-%d"),
                            "action": "BUY", "ticker": t,
                            "value": round(diff, 2), "fee": round(fee, 2),
                            "reason": "Signal → BUY",
                        })
                elif diff < -10:  # Sell excess
                    excess_qty = abs(diff) / price
                    proceeds = excess_qty * price
                    fee = proceeds * TAKER_FEE
                    cash += proceeds - fee
                    holdings[t] = holdings.get(t, 0) - excess_qty
                    trades.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "action": "SELL", "ticker": t,
                        "value": round(proceeds, 2), "fee": round(fee, 2),
                        "reason": "Rebalance trim",
                    })

        # Recalculate after rebalance
        stock_val = sum(holdings.get(t,0)*prices_now.get(t,0) for t in holdings)
        port_val  = cash + stock_val
        equity_curve.append({"date": date.strftime("%Y-%m-%d"), "value": round(port_val, 2)})

    return equity_curve, btc_eq_curve, trades, signals

# ── Current signals ───────────────────────────────────────────────────────────
def get_current_signals(price_data, signals):
    now = pd.Timestamp.now(tz="UTC")
    universe = get_universe(now)
    current = {}
    for t in list(universe) + ["BTC", "PAXG"]:
        if t in signals:
            mask = signals[t].index <= now
            if mask.any():
                current[t] = signals[t][mask].iloc[-1]
    return current

# ── Output ────────────────────────────────────────────────────────────────────
def build_output(equity_curve, btc_eq_curve, trades, signals, price_data):
    if not equity_curve:
        print("No equity curve generated.")
        return

    final_val = equity_curve[-1]["value"]
    total_ret = (final_val / STARTING_CAPITAL - 1) * 100

    # Stats
    rets = pd.Series([e["value"] for e in equity_curve]).pct_change().dropna()
    sharpe = (rets.mean() / rets.std() * (252**0.5)) if rets.std() > 0 else 0
    roll_max = pd.Series([e["value"] for e in equity_curve]).cummax()
    drawdowns = (pd.Series([e["value"] for e in equity_curve]) - roll_max) / roll_max
    max_dd = drawdowns.min() * 100

    n_days = len(equity_curve)
    cagr = ((final_val / STARTING_CAPITAL) ** (365 / max(n_days, 1)) - 1) * 100

    current_sigs = get_current_signals(price_data, signals)
    btc_sig  = current_sigs.get("BTC", "SELL")
    paxg_sig = current_sigs.get("PAXG", "SELL")

    print(f"\n{'─'*52}")
    print(f"  Daily Strategy Backtest (2Y)")
    print(f"  Portfolio:     ${final_val:,.2f}")
    print(f"  Total Return:  {total_ret:+.2f}%")
    print(f"  CAGR:          {cagr:+.2f}%")
    print(f"  Sharpe:        {sharpe:.2f}")
    print(f"  Max Drawdown:  {max_dd:.2f}%")
    print(f"  Total Trades:  {len(trades)}")
    print(f"\n  BTC Gate: {btc_sig}  |  PAXG: {paxg_sig}")
    buy_sigs  = [t for t,s in current_sigs.items() if s=="BUY" and t not in ("BTC","PAXG")]
    sell_sigs = [t for t,s in current_sigs.items() if s=="SELL" and t not in ("BTC","PAXG")]
    print(f"  BUY  ({len(buy_sigs)}): {', '.join(sorted(buy_sigs))}")
    print(f"  SELL ({len(sell_sigs)}): {', '.join(sorted(sell_sigs))}")
    print(f"{'─'*52}")

    # portfolios_daily.json
    portfolio = {
        "id":               PORTFOLIO_ID,
        "generated":        datetime.now(timezone.utc).isoformat(),
        "final_value":      round(final_val, 2),
        "total_return_pct": round(total_ret, 2),
        "cagr_pct":         round(cagr, 2),
        "sharpe_ratio":     round(sharpe, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "equity_curve":     equity_curve,
        "btc_equity_curve": btc_eq_curve,
        "current_signals":  {k: str(v) for k,v in current_sigs.items()},
        "btc_signal":       btc_sig,
        "paxg_signal":      paxg_sig,
    }

    output = {"portfolios": [portfolio]}
    with open("portfolios_daily.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print("✓ portfolios_daily.json written")

    # trade_history_daily.json
    total_fees = sum(t.get("fee", 0) for t in trades)
    trade_history = {
        "generated":        datetime.now(timezone.utc).isoformat(),
        "portfolio_id":     PORTFOLIO_ID,
        "starting_capital": STARTING_CAPITAL,
        "final_value":      round(final_val, 2),
        "total_return_pct": round(total_ret, 2),
        "total_fees":       round(total_fees, 2),
        "equity_curve":     equity_curve,
        "btc_equity_curve": btc_eq_curve,
        "trades":           list(reversed(trades)),
    }
    with open("trade_history_daily.json", "w") as f:
        json.dump(trade_history, f, indent=2, default=str)
    print("✓ trade_history_daily.json written")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("DMG Capital — Daily Strategy Engine")
    print(f"Starting capital: ${STARTING_CAPITAL:,.2f}")
    print(f"Indicators: EMA{EMA_FAST}/{EMA_SLOW}, RSI{RSI_N}, MACD{MACD_FAST}/{MACD_SLOW}/{MACD_SIG}")

    price_data = fetch_all_daily()
    print(f"\nGot data for {len(price_data)}/{len(ALL_TICKERS)} tickers")

    print("\nRunning daily backtest (last 2 years)...")
    equity_curve, btc_eq_curve, trades, signals = run_backtest(price_data)

    build_output(equity_curve, btc_eq_curve, trades, signals, price_data)

#!/usr/bin/env python3
"""
DMG Capital — Daily Executor (Test Build)
Reads signals from portfolios_daily.json and executes on Kraken.
Designed for small live testing ($1,000 starting capital).

Usage:
  Paper:  python executor_daily.py
  Live:   python executor_daily.py --live
"""

import json
import os
import subprocess
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
SIGNALS_FILE     = "portfolios_daily.json"
PORTFOLIO_ID     = "crypto-rotation-daily"
LOG_FILE         = Path("execution_log_daily.jsonl")
PAPER_STATE_REPO = Path("paper_state_daily.json")
DRIFT_THRESHOLD  = 0.03
MIN_ORDER_USD    = 2.0       # Lower minimum for small account
SLEEP_BETWEEN    = 1.5
TAKER_FEE        = 0.0026

PAPER_STATE_CANDIDATES = [
    Path.home() / ".local/share/kraken-cli/paper.db",
    Path.home() / ".local/share/kraken/paper.db",
    Path.home() / "Library/Application Support/kraken-cli/paper.db",
    Path.home() / ".config/kraken/paper.db",
    Path.home() / ".config/kraken-cli/paper.db",
]

PAIR_MAP = {
    "BTC":"BTCUSD","ETH":"ETHUSD","XRP":"XRPUSD","SOL":"SOLUSD",
    "DOGE":"DOGEUSD","ADA":"ADAUSD","TRX":"TRXUSD","AVAX":"AVAXUSD",
    "LINK":"LINKUSD","BCH":"BCHUSD","PAXG":"PAXGUSD","LTC":"LTCUSD",
    "DOT":"DOTUSD","XLM":"XLMUSD","XMR":"XMRUSD",
}

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("dmg-daily-executor")

LIVE = "--live" in sys.argv
MODE = "LIVE" if LIVE else "PAPER"
CMD  = "order" if LIVE else "paper"

# ── Kraken CLI ────────────────────────────────────────────────────────────────
def kraken(args):
    full_cmd = ["kraken", CMD] + args + ["--output", "json"]
    log.debug(f"CMD: {' '.join(full_cmd)}")
    env = os.environ.copy()
    result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=30, env=env)
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode != 0:
        raise RuntimeError(f"Kraken CLI error: {stderr or stdout or 'no output'}")
    if not stdout:
        raise RuntimeError(f"Empty output. stderr: {stderr}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"raw": stdout}

def get_price(ticker):
    pair = PAIR_MAP.get(ticker)
    if not pair:
        return None
    full_cmd = ["kraken", "ticker", pair, "--output", "json"]
    result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=30)
    raw = result.stdout.strip()
    if result.returncode != 0:
        return None
    try:
        data = json.loads(raw)
        for key, val in data.items():
            if isinstance(val, dict):
                c = val.get("c")
                if c and len(c) > 0:
                    return float(c[0])
                a = val.get("a")
                if a and len(a) > 0:
                    return float(a[0])
        return None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None

def get_balances():
    data = kraken(["balance"])
    log.debug(f"Balance: {json.dumps(data)[:300]}")
    balances = {}
    raw_balances = data.get("balances") or {}

    if isinstance(raw_balances, dict):
        raw = {}
        for asset, info in raw_balances.items():
            clean = asset.upper().replace("XBT","BTC").replace("XXBT","BTC")
            try:
                qty = float(info.get("total") or info.get("available") or 0)
            except (ValueError, TypeError):
                qty = 0
            if qty > 0:
                raw[clean] = qty
        if "USD" in raw:
            balances["USD"] = raw["USD"]
        for asset, qty in raw.items():
            if asset == "USD":
                continue
            price = get_price(asset)
            if price and qty > 0:
                usd_val = round(qty * price, 2)
                if usd_val > 0.01:
                    balances[asset] = usd_val
            else:
                log.warning(f"Could not price {asset}")

    if not balances:
        log.warning("No balances — fresh paper account assumed")
        balances["USD"] = 1000.0

    return balances

def get_total(balances):
    return sum(balances.values())

def place_sell(ticker, amount_usd):
    pair  = PAIR_MAP.get(ticker)
    if not pair: raise ValueError(f"No pair for {ticker}")
    price = get_price(ticker)
    if not price: raise ValueError(f"No price for {ticker}")
    qty = round(amount_usd / price, 8)
    log.info(f"  SELL {ticker}  qty={qty}  ~${amount_usd:,.2f}")
    return kraken(["sell", pair, str(qty), "--type", "market"])

def place_buy(ticker, amount_usd):
    pair  = PAIR_MAP.get(ticker)
    if not pair: raise ValueError(f"No pair for {ticker}")
    price = get_price(ticker)
    if not price: raise ValueError(f"No price for {ticker}")
    spendable = amount_usd / (1 + TAKER_FEE)
    qty = round(spendable / price, 8)
    log.info(f"  BUY  {ticker}  qty={qty}  ~${spendable:,.2f}")
    return kraken(["buy", pair, str(qty), "--type", "market"])

# ── Paper state ───────────────────────────────────────────────────────────────
def restore_paper_state():
    import shutil
    if not PAPER_STATE_REPO.exists():
        # First run — read starting capital from signal engine output
        start_balance = 1000.0
        try:
            with open(SIGNALS_FILE) as f:
                pdata = json.load(f)
            p = next((x for x in pdata.get("portfolios",[]) if x["id"]==PORTFOLIO_ID), None)
            if p:
                curve = p.get("equity_curve", [])
                if curve:
                    start_balance = float(curve[-1]["value"])
                    log.info(f"Using backtest end value: ${start_balance:,.2f}")
        except Exception as e:
            log.warning(f"Could not read backtest end ({e}) — using $1,000")

        result = subprocess.run(
            ["kraken", "paper", "init", "--balance", str(round(start_balance, 2)), "--output", "json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(f"Paper init failed: {result.stderr.strip()}")
        log.info(f"Paper account initialised at ${start_balance:,.2f} ✓")
        return

    with open(PAPER_STATE_REPO) as f:
        snapshot = json.load(f)

    total_value = snapshot.get("total_value", 1000)
    positions   = snapshot.get("positions", {})
    log.info(f"Restoring: ${total_value:,.2f}, {len(positions)} positions")

    subprocess.run(["kraken", "paper", "reset"], capture_output=True, timeout=10)
    result = subprocess.run(
        ["kraken", "paper", "init", "--balance", str(round(total_value, 2)), "--output", "json"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        log.warning("Paper init failed — starting fresh")
        subprocess.run(["kraken", "paper", "init", "--balance", "1000"], capture_output=True)
        return

    for ticker, usd_val in positions.items():
        if ticker == "USD" or usd_val < MIN_ORDER_USD:
            continue
        pair = PAIR_MAP.get(ticker)
        if not pair:
            continue
        price = get_price(ticker)
        if not price:
            continue
        spendable = usd_val / (1 + TAKER_FEE)
        qty = round(spendable / price, 8)
        r = subprocess.run(
            ["kraken", "paper", "buy", pair, str(qty), "--type", "market", "--output", "json"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0:
            log.info(f"  Restored {ticker}: {qty} @ ~${usd_val:,.2f}")
        else:
            log.warning(f"  Could not restore {ticker}: {r.stderr.strip()[:80]}")
    log.info("Paper state restored ✓")

def backup_paper_state():
    result = subprocess.run(
        ["kraken", "paper", "balance", "--output", "json"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        log.warning(f"Could not read paper balance: {result.stderr.strip()}")
        return
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        log.warning("Could not parse paper balance")
        return

    raw_balances = data.get("balances", {})
    positions = {}
    total_value = 0.0

    if isinstance(raw_balances, dict):
        for asset, info in raw_balances.items():
            clean = asset.upper().replace("XBT","BTC").replace("XXBT","BTC")
            try:
                qty = float(info.get("total") or info.get("available") or 0)
            except (ValueError, TypeError):
                qty = 0
            if qty <= 0:
                continue
            if clean == "USD":
                positions["USD"] = qty
                total_value += qty
            else:
                price = get_price(clean)
                if price:
                    usd_val = round(qty * price, 2)
                    positions[clean] = usd_val
                    total_value += usd_val

    snapshot = {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "total_value": round(total_value, 2),
        "positions":   positions,
    }
    with open(PAPER_STATE_REPO, "w") as f:
        json.dump(snapshot, f, indent=2)
    log.info(f"Backed up paper state: ${total_value:,.2f} → {PAPER_STATE_REPO}")

# ── Signal fetch ──────────────────────────────────────────────────────────────
def fetch_signals():
    path = Path(SIGNALS_FILE)
    if not path.exists():
        raise FileNotFoundError(f"{SIGNALS_FILE} not found — run crypto_portfolio_daily.py first")
    with open(path) as f:
        data = json.load(f)
    portfolios = data.get("portfolios", [])
    p = next((x for x in portfolios if x["id"] == PORTFOLIO_ID), None)
    if not p:
        raise ValueError(f"Portfolio '{PORTFOLIO_ID}' not found")
    return p

# ── Rebalance ─────────────────────────────────────────────────────────────────
def compute_rebalance(current_balances, target_tickers, total_usd):
    n = len(target_tickers)
    if n == 0:
        return [], []

    target_usd   = {t: total_usd / n for t in target_tickers}
    sells, buys  = [], []
    held_tickers = {t for t, v in current_balances.items()
                    if t != "USD" and v >= MIN_ORDER_USD}

    # Flipped SELL — liquidate fully
    flipped_sell  = held_tickers - set(target_tickers)
    sell_proceeds = 0.0
    for ticker in sorted(flipped_sell):
        val = current_balances[ticker]
        sells.append((ticker, val))
        sell_proceeds += val
        log.info(f"  {ticker}: SELL full ${val:,.2f} (signal → SELL)")

    # New BUY signals
    new_buys     = sorted(set(target_tickers) - held_tickers)
    new_buy_cost = sum(target_usd[t] for t in new_buys)
    for ticker in new_buys:
        buys.append((ticker, target_usd[ticker]))
        log.info(f"  {ticker}: BUY new ${target_usd[ticker]:,.2f}")

    # Fund gap by trimming overweight positions
    funding_gap   = max(0.0, new_buy_cost - sell_proceeds)
    remaining_gap = funding_gap
    still_held    = sorted(held_tickers & set(target_tickers))

    overweights = []
    for ticker in still_held:
        current_val = current_balances[ticker]
        target      = target_usd[ticker]
        excess      = current_val - target
        drift_pct   = (current_val - target) / total_usd
        overweights.append((ticker, current_val, target, excess, drift_pct))
    overweights.sort(key=lambda x: x[3], reverse=True)

    for ticker, current_val, target, excess, drift_pct in overweights:
        if remaining_gap > MIN_ORDER_USD and excess > MIN_ORDER_USD:
            trim_amt = min(excess, remaining_gap)
            sells.append((ticker, trim_amt))
            remaining_gap -= trim_amt
            log.info(f"  {ticker}: TRIM ${trim_amt:,.2f} to fund new buys")
        elif abs(drift_pct) > DRIFT_THRESHOLD:
            delta = current_val - target
            if delta > MIN_ORDER_USD:
                sells.append((ticker, delta))
                log.info(f"  {ticker}: TRIM ${delta:,.2f} (drift {drift_pct:+.1%})")
            elif delta < -MIN_ORDER_USD:
                buys.append((ticker, abs(delta)))
                log.info(f"  {ticker}: TOP UP ${abs(delta):,.2f}")
        else:
            log.info(f"  {ticker}: HOLD (drift {drift_pct:+.1%})")

    return sells, buys

# ── Logging ───────────────────────────────────────────────────────────────────
def _log_execution(now, signals, target, defensive, sells, buys, total, status):
    entry = {
        "timestamp":      now.isoformat(),
        "mode":           MODE,
        "status":         status,
        "btc_signal":     signals.get("BTC"),
        "paxg_signal":    signals.get("PAXG"),
        "defensive":      defensive,
        "target_tickers": target,
        "total_usd":      round(total, 2),
        "sells":          sells,
        "buys":           buys,
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    log.info(f"✓ Logged to {LOG_FILE}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    now = datetime.now(timezone.utc)
    log.info("=" * 52)
    log.info(f"DMG Daily Executor — {MODE} mode")
    log.info(f"Time: {now.isoformat()}")
    log.info("=" * 52)

    if LIVE:
        log.warning("⚠ LIVE MODE — real orders on Kraken")
        confirm = input("Type YES to continue: ")
        if confirm.strip() != "YES":
            log.info("Aborted.")
            return

    # 1. Fetch signals
    try:
        portfolio = fetch_signals()
    except Exception as e:
        log.error(f"Failed to fetch signals: {e}")
        sys.exit(1)

    signals     = portfolio.get("current_signals", {})
    btc_signal  = signals.get("BTC", "SELL")
    paxg_signal = signals.get("PAXG", "SELL")
    generated   = portfolio.get("generated", "unknown")

    log.info(f"Signals from: {generated}")
    log.info(f"BTC gate:     {btc_signal}")
    log.info(f"PAXG signal:  {paxg_signal}")

    # 2. Determine target
    if btc_signal == "BUY":
        target_tickers = sorted([
            t for t, s in signals.items()
            if s == "BUY" and t != "PAXG"
        ])
        defensive = None
        log.info(f"Gate OPEN  — target: {', '.join(target_tickers)}")
    else:
        if paxg_signal == "BUY":
            target_tickers = ["PAXG"]
            defensive = "PAXG"
            log.info("Gate CLOSED — defensive: PAXG")
        else:
            target_tickers = []
            defensive = "USDT"
            log.info("Gate CLOSED — defensive: USDT")

    # 3. Restore paper state
    if not LIVE:
        restore_paper_state()

    # 4. Get balances
    try:
        balances = get_balances()
        total    = get_total(balances)
        log.info(f"Current balance: ${total:,.2f}")
        for t, v in sorted(balances.items()):
            log.info(f"  {t}: ${v:,.2f} ({v/total*100:.1f}%)")
    except Exception as e:
        log.error(f"Failed to get balances: {e}")
        sys.exit(1)

    if total < MIN_ORDER_USD:
        log.error(f"Balance ${total:.2f} too low")
        sys.exit(1)

    # 5. Compute rebalance
    if not target_tickers:
        sells = [(t, v) for t, v in balances.items() if t != "USD" and v > MIN_ORDER_USD]
        buys  = []
        if sells:
            log.info(f"Moving to {defensive} — selling {len(sells)} position(s)")
    else:
        sells, buys = compute_rebalance(balances, target_tickers, total)

    if not sells and not buys:
        log.info("✓ No rebalance needed")
        if not LIVE:
            backup_paper_state()
        _log_execution(now, signals, target_tickers, defensive, [], [], total, "NO_CHANGE")
        return

    log.info(f"Plan: {len(sells)} sell(s), {len(buys)} buy(s)")

    # 6. Execute sells
    sell_results = []
    for ticker, usd_val in sells:
        try:
            place_sell(ticker, usd_val)
            sell_results.append({"ticker": ticker, "usd": round(usd_val, 2), "status": "ok"})
            time.sleep(SLEEP_BETWEEN)
        except Exception as e:
            log.error(f"  SELL {ticker} failed: {e}")
            sell_results.append({"ticker": ticker, "usd": round(usd_val, 2), "status": "error", "error": str(e)})

    if sells:
        log.info("Waiting 3s for sells to settle...")
        time.sleep(3)

    # 7. Refresh balance
    try:
        balances = get_balances()
        total    = get_total(balances)
        log.info(f"Post-sell balance: ${total:,.2f}")
    except Exception as e:
        log.warning(f"Could not refresh: {e}")

    # 8. Execute buys — dynamic sizing
    buy_results = []
    remaining_buys = [b for b in buys if b[1] >= MIN_ORDER_USD]
    for idx, (ticker, _) in enumerate(remaining_buys):
        try:
            fresh = get_balances()
            avail_usd = fresh.get("USD", 0)
        except Exception:
            avail_usd = balances.get("USD", 0)
        buys_left = len(remaining_buys) - idx
        usd_amt   = (avail_usd - 0.50) / buys_left  # $0.50 buffer for small accounts
        if usd_amt < MIN_ORDER_USD:
            log.warning(f"  Skip {ticker} — ${usd_amt:.2f} below minimum")
            buy_results.append({"ticker": ticker, "usd": round(usd_amt, 2), "status": "skip"})
            continue
        try:
            place_buy(ticker, usd_amt)
            buy_results.append({"ticker": ticker, "usd": round(usd_amt, 2), "status": "ok"})
            time.sleep(SLEEP_BETWEEN)
        except Exception as e:
            log.error(f"  BUY {ticker} failed: {e}")
            buy_results.append({"ticker": ticker, "usd": round(usd_amt, 2), "status": "error", "error": str(e)})

    # 9. Backup state
    if not LIVE:
        backup_paper_state()

    # 10. Summary
    log.info("=" * 52)
    log.info("Execution complete")
    log.info(f"  Sells: {sum(1 for r in sell_results if r['status']=='ok')}/{len(sell_results)}")
    log.info(f"  Buys:  {sum(1 for r in buy_results  if r['status']=='ok')}/{len(buy_results)}")
    log.info("=" * 52)

    _log_execution(now, signals, target_tickers, defensive,
                   sell_results, buy_results, total, "EXECUTED")

if __name__ == "__main__":
    main()

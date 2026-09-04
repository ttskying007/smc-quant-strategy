#!/usr/bin/env python3
"""
全维度交叉回测: 3周期 × 3时间窗口 × 全量4836只
周期: daily, 60min, weekly
窗口: full(全量), mid(最近150bar), recent(最近50bar)
信号: OB_Bull (已验证 WR=94.2%)
策略: T+1开盘买, SL=OB.lower*0.995, TP=close*1.03, 5bar超时
"""

import json, os, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/root/.hermes")
CACHE = ROOT / "kline_cache"
SCRIPTS = ROOT / "scripts/v11"
OUTPUT = ROOT / "smc_opt_v21"

sys.path.insert(0, str(SCRIPTS))
from signals_v20 import detect_all_signals_v20

TIMEFRAMES = ["daily", "60min", "weekly"]
WINDOWS = ["full", "mid", "recent"]
WINDOW_SIZES = {"full": None, "mid": 150, "recent": 50}

TP_PCT = 0.03
SL_FACTOR = 0.995
MAX_HOLD = 5


def load_klines(symbol, tf):
    """Load klines for a symbol+timeframe. Returns list of {o,h,l,c} or None."""
    prefix = symbol[:2]
    if tf == "daily":
        path = CACHE / f"{symbol}_daily_300.json"
    elif tf == "60min":
        path = CACHE / f"{symbol}_60min_500.json"
    elif tf == "weekly":
        path = CACHE / f"{symbol}_weekly_200.json"

    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
    except Exception:
        return None

    # Normalize to [{o,h,l,c}]
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["qfqday", "qfqweek", "data", "kline"]:
            if key in data and isinstance(data[key], list):
                return data[key]
        # Try generic first array
        for v in data.values():
            if isinstance(v, list) and len(v) > 0:
                return v
    return None


def run_backtest(ohlcv, signals, window_slice=None):
    """Run OB_Bull backtest on ohlcv data. Returns trades list."""
    if window_slice:
        start, end = window_slice
        ohlcv = ohlcv[start:end]
        # Adjust signal indices to window
        signals = [s for s in signals if start <= s["idx"] < end]
        for s in signals:
            s["idx"] -= start

    trades = []
    used_bars = set()
    N = len(ohlcv)

    for sig in signals:
        if sig["idx"] not in used_bars and sig["idx"] + 1 < N:
            entry_idx = sig["idx"] + 1  # T+1
            entry_price = ohlcv[entry_idx]["o"]
            sl_price = sig.get("lower", entry_price * 0.995) * SL_FACTOR
            tp_price = entry_price * (1 + TP_PCT)

            # Simulate exit
            won = False
            exit_idx = entry_idx
            exit_price = entry_price

            for j in range(entry_idx + 1, min(entry_idx + MAX_HOLD + 1, N)):
                bar = ohlcv[j]
                if bar["l"] <= sl_price:
                    exit_idx = j
                    exit_price = sl_price
                    break
                if bar["h"] >= tp_price:
                    exit_idx = j
                    exit_price = tp_price
                    won = True
                    break
            else:
                # Time stop
                exit_idx = min(entry_idx + MAX_HOLD, N - 1)
                exit_price = ohlcv[exit_idx]["c"]
                won = exit_price > entry_price

            pnl_pct = (exit_price - entry_price) / entry_price * 100
            trades.append({
                "entry_idx": entry_idx,
                "exit_idx": exit_idx,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl_pct": pnl_pct,
                "won": won,
                "hold": exit_idx - entry_idx,
            })
            used_bars.add(sig["idx"])

    return trades


def backtest_stock(symbol):
    """Run full cross-cycle backtest for one stock."""
    results = {}
    for tf in TIMEFRAMES:
        ohlcv = load_klines(symbol, tf)
        if ohlcv is None or len(ohlcv) < 50:
            continue

        # Detect OB_Bull signals
        all_sigs = detect_all_signals_v20(ohlcv)
        ob_bull = all_sigs.get("OB_Bull", [])

        if not ob_bull:
            continue

        tf_result = {}
        for win_name, win_size in WINDOW_SIZES.items():
            if win_size is None:
                trades = run_backtest(ohlcv, ob_bull)
            elif len(ohlcv) > win_size:
                start = len(ohlcv) - win_size
                trades = run_backtest(ohlcv, ob_bull, (start, len(ohlcv)))
            else:
                trades = run_backtest(ohlcv, ob_bull)

            if trades:
                won = sum(1 for t in trades if t["won"])
                total = len(trades)
                wr = won / total * 100
                avg_pnl = sum(t["pnl_pct"] for t in trades) / total
                avg_hold = sum(t["hold"] for t in trades) / total
                tp_count = sum(1 for t in trades if t["exit_price"] >= t["entry_price"] * (1 + TP_PCT * 0.99))

                tf_result[win_name] = {
                    "trades": total,
                    "won": won,
                    "wr": round(wr, 1),
                    "avg_pnl": round(avg_pnl, 2),
                    "avg_hold": round(avg_hold, 1),
                    "tp_rate": round(tp_count / total * 100, 1),
                }

        if tf_result:
            results[tf] = tf_result

    return results if results else None


def main():
    # Get all symbols from kline cache
    symbols = set()
    for f in CACHE.glob("*_daily_300.json"):
        s = f.stem.replace("_daily_300", "")
        symbols.add(s)

    symbols = sorted(symbols)
    print(f"Total stocks: {len(symbols)}")

    all_results = {}
    stats = defaultdict(lambda: defaultdict(lambda: {"trades": 0, "won": 0, "total_pnl": 0.0, "total_hold": 0, "tp": 0, "stocks": 0}))

    for i, sym in enumerate(symbols):
        r = backtest_stock(sym)
        if r:
            all_results[sym] = r
            for tf, windows in r.items():
                for win, wdata in windows.items():
                    s = stats[tf][win]
                    s["trades"] += wdata["trades"]
                    s["won"] += wdata["won"]
                    s["total_pnl"] += wdata["avg_pnl"] * wdata["trades"]
                    s["total_hold"] += wdata["avg_hold"] * wdata["trades"]
                    s["tp"] += int(wdata["tp_rate"] > 50)
                    s["stocks"] += 1

        if (i + 1) % 500 == 0:
            print(f"  Progress: {i+1}/{len(symbols)}")

    # Aggregate stats
    print(f"\nTotal stocks with results: {len(all_results)}")

    for tf in TIMEFRAMES:
        print(f"\n{'='*60}")
        print(f"  {tf.upper()}")
        print(f"{'='*60}")
        print(f"  {'Window':<10} {'Stocks':>7} {'Trades':>7} {'WR':>7} {'Avg PnL':>8} {'Hold':>6} {'TP%':>6}")
        print(f"  {'-'*50}")
        for win in WINDOWS:
            s = stats[tf][win]
            if s["stocks"] == 0:
                continue
            wr = s["won"] / s["trades"] * 100 if s["trades"] else 0
            avg_pnl = s["total_pnl"] / s["trades"] if s["trades"] else 0
            avg_hold = s["total_hold"] / s["trades"] if s["trades"] else 0
            tp_rate = s["tp"] / s["stocks"] * 100 if s["stocks"] else 0
            print(f"  {win:<10} {s['stocks']:>7} {s['trades']:>7} {wr:>6.1f}% {avg_pnl:>+7.2f}% {avg_hold:>5.1f}b {tp_rate:>5.1f}%")

    # Per-stock breakdown (top stocks by full-daily WR)
    stock_ranking = []
    for sym, r in all_results.items():
        if "daily" in r and "full" in r["daily"]:
            wr = r["daily"]["full"]["wr"]
            trades = r["daily"]["full"]["trades"]
            stock_ranking.append((wr, trades, sym))

    stock_ranking.sort(reverse=True)
    print(f"\n{'='*60}")
    print(f"  TOP 20 Stocks (daily full window)")
    print(f"{'='*60}")
    print(f"  {'Symbol':<12} {'Trades':>7} {'WR':>7}")
    for wr, trades, sym in stock_ranking[:20]:
        print(f"  {sym:<12} {trades:>7} {wr:>6.1f}%")

    # Save results
    os.makedirs(str(OUTPUT), exist_ok=True)
    output_path = OUTPUT / "cross_cycle_v4.json"
    output = {
        "summary": {tf: {win: {"stocks": s["stocks"], "trades": s["trades"],
                              "wr": round(s["won"]/s["trades"]*100 if s["trades"] else 0, 1),
                              "avg_pnl": round(s["total_pnl"]/s["trades"] if s["trades"] else 0, 2),
                              "avg_hold": round(s["total_hold"]/s["trades"] if s["trades"] else 0, 1)}
                         for win, s in windows.items()
                         if s["stocks"] > 0}
                    for tf, windows in stats.items()},
        "top_stocks": [{"sym": s, "trades": t, "wr": w} for w, t, s in stock_ranking[:50]],
        "per_stock": all_results,
    }
    with open(output_path, "w") as f:
        json.dump(output, f, ensure_ascii=False)
    print(f"\nResults saved: {output_path}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Dimension B: state-dependent execution. Monthly WEAK -> hold longer (bounce space),
STRONG -> standard hold. Uses event-trades? No: this is for SMC momentum; recompute
hold-period PnL per monthly state from TP2 tencent trades data (mark-to-market path).
Simplified: for each trade, compute PnL at hold 5/10/15/20 per monthly state."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
            out.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"])})
    out.sort(key=lambda b: b["t"])
    return out


def monthly_agg(daily):
    months = []
    cur = None
    for b in daily:
        m = b["t"][:6]
        if cur is None or cur["m"] != m:
            if cur:
                months.append(cur)
            cur = {"m": m, "h": b["h"], "l": b["l"], "c": b["c"]}
        else:
            cur["h"] = max(cur["h"], b["h"])
            cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]
    if cur:
        months.append(cur)
    return months


def monthly_state(months, day_date):
    m0 = day_date[:6]
    prior = [m for m in months if m["m"] < m0]
    if len(prior) < 6:
        return None
    last = prior[-3:]
    strong = last[-1]["h"] > last[0]["h"] and last[-1]["l"] > last[0]["l"]
    win = prior[-6:]
    mid = min(w["l"] for w in win) + (max(w["h"] for w in win) - min(w["l"] for w in win)) * 0.5
    strong = strong or prior[-1]["c"] > mid
    return "STRONG" if strong else "WEAK"


# load SMC momentum trades (TP2 tencent) with entry date + symbol
trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

cache = {}
def state_of(symbol, entry_date):
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    if fn not in cache:
        p = os.path.join(KT, fn)
        if not os.path.exists(p):
            cache[fn] = None
            return None
        cache[fn] = monthly_agg(bars(p))
    months = cache[fn]
    if months is None:
        return None
    return monthly_state(months, str(entry_date))


# for each trade, compute forward pnl at holds 5/10/15/20 (entry open -> close at k)
fwd_cache = {}
def fwd_pnl(symbol, entry_date, hold):
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    if fn not in fwd_cache:
        p = os.path.join(KT, fn)
        if not os.path.exists(p):
            fwd_cache[fn] = []
            return None
        bs = bars(p)
        fwd_cache[fn] = ([b["t"] for b in bs], [b["o"] for b in bs], [b["c"] for b in bs])
    dates, opens, closes = fwd_cache[fn]
    if entry_date not in dates:
        prev = [d for d in dates if d < entry_date]
        if not prev:
            return None
        i = dates.index(prev[-1])
    else:
        i = dates.index(entry_date)
    if i + hold >= len(closes):
        return None
    return (closes[i + hold] / opens[i] - 1) * 100 - 0.20


rows = []
for t in trades:
    st = state_of(t["symbol"], t["entry_date"])
    if st is None:
        continue
    for h in (5, 10, 15, 20):
        pnl = fwd_pnl(t["symbol"], t["entry_date"], h)
        if pnl is not None:
            rows.append({"state": st, "hold": h, "pnl": pnl, "entry_date": t["entry_date"]})

print(f"rows: {len(rows)}")
print("\n=== 月线状态 × 持有期（SMC 动量）===")
for st in ("WEAK", "STRONG"):
    for h in (5, 10, 15, 20):
        rs = [r for r in rows if r["state"] == st and r["hold"] == h]
        if len(rs) < 50:
            continue
        avg = sum(r["pnl"] for r in rs) / len(rs)
        w = sum(1 for r in rs if r["pnl"] > 0)
        by_y = defaultdict(list)
        for r in rs:
            by_y[str(r["entry_date"])[:4]].append(r["pnl"])
        ys = " ".join(f"{y}:{sum(v)/len(v):+.1f}" for y, v in sorted(by_y.items()) if len(v) >= 20)
        print(f"  {st} hold={h}: n={len(rs)} WR={100*w/len(rs):.0f}% avg={avg:+.2f}% | {ys}")

# -*- coding: utf-8 -*-
"""Dimension A fix: use TP2_tencent_trades (already replayed) + tag monthly permission.
Compare baseline vs monthly-filtered."""
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
            cur = {"m": m, "t": b["t"], "h": b["h"], "l": b["l"], "c": b["c"]}
        else:
            cur["h"] = max(cur["h"], b["h"])
            cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]
    if cur:
        months.append(cur)
    return months


def monthly_perm(months, day_date):
    m0 = day_date[:6]
    prior = [m for m in months if m["m"] < m0]
    if len(prior) < 6:
        return False
    last = prior[-3:]
    if last[-1]["h"] > last[0]["h"] and last[-1]["l"] > last[0]["l"]:
        return True
    win = prior[-6:]
    mid = min(w["l"] for w in win) + (max(w["h"] for w in win) - min(w["l"] for w in win)) * 0.5
    return prior[-1]["c"] > mid


# load TP2 tencent trades (these are the SMC momentum trades, r20 filtered already in the run)
trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        r["t1_violation"] = str(r.get("t1_violation", "")).lower() in ("true", "1", "yes")
        trades.append(r)

# tag monthly permission per trade (entry date)
cache = {}
def monthly_ok(symbol, entry_date):
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
    return monthly_perm(months, str(entry_date))

for t in trades:
    t["monthly"] = monthly_ok(t["symbol"], t["entry_date"])


def report(label, rs):
    if len(rs) < 200:
        print(f"{label}: n={len(rs)} (过小)"); return
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"]).startswith(y)]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("=== 月线层（基于腾讯回放交易）===")
print(f"总交易: {len(trades)}")
report("基线（全部 TP2）", trades)
report("月线权限（月线HH/HL或>mid）", [t for t in trades if t["monthly"] is True])
report("无月线权限", [t for t in trades if t["monthly"] is False])

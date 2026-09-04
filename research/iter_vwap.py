# -*- coding: utf-8 -*-
"""Dimension D: VWAP assistance (user-named 'vagaas tunnel').
VWAP = cumulative volume-weighted average price (session or rolling).
Test on SMC momentum (TP2-R20 trades): 
1) VWAP deviation at entry (price vs VWAP) as quality split
2) VWAP tunnel (VWAP +/- 1 bandwidth) as TP reference
Note: VWAP is lagging (cumulative) and can be deceptive in ranging markets."""
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
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            out.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
    out.sort(key=lambda b: b["t"])
    return out


def rolling_vwap(daily, idx, window=20):
    """20-day rolling VWAP at bar idx (uses idx and prior bars, PIT)."""
    if idx < window:
        return None, None
    pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(idx - window + 1, idx + 1))
    vol = sum(daily[k]["v"] for k in range(idx - window + 1, idx + 1))
    if vol <= 0:
        return None, None
    return pv / vol, vol


# load SMC momentum trades
trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        r["t1_violation"] = str(r.get("t1_violation", "")).lower() in ("true", "1", "yes")
        trades.append(r)

# r20 filter (recompute)
closes_cache = {}
def r20_of(symbol, entry_date):
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    if fn not in closes_cache:
        p = os.path.join(KT, fn)
        if not os.path.exists(p):
            closes_cache[fn] = []
            return None
        raw = json.load(open(p, encoding="utf-8"))
        cl = [(("".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]), float(r["c"])) for r in raw if r.get("t") and r.get("c")]
        cl.sort()
        closes_cache[fn] = cl
    cl = closes_cache[fn]
    ds = [c[0] for c in cl]
    if entry_date not in ds:
        prev = [d for d in ds if d < entry_date]
        if not prev:
            return None
        i = ds.index(prev[-1])
    else:
        i = ds.index(entry_date) - 1
    if i < 20:
        return None
    return cl[i][1] / cl[i - 20][1] - 1


# vwap cache
vwap_cache = {}
def vwap_at(symbol, entry_date):
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    if fn not in vwap_cache:
        p = os.path.join(KT, fn)
        if not os.path.exists(p):
            vwap_cache[fn] = None
            return None, None
        vwap_cache[fn] = bars(p)
    bs = vwap_cache[fn]
    dates = [b["t"] for b in bs]
    if entry_date not in dates:
        prev = [d for d in dates if d < entry_date]
        if not prev:
            return None, None
        i = dates.index(prev[-1])
    else:
        i = dates.index(entry_date)
    return rolling_vwap(bs, i, 20)


for t in trades:
    t["r20"] = r20_of(t["symbol"], t["entry_date"])
    vw, _ = vwap_at(t["symbol"], t["entry_date"])
    t["vwap"] = vw

r20_trades = [t for t in trades if t["r20"] is not None and 0 <= t["r20"] < 0.15 and t["vwap"] is not None]
print("TP2-R20 (vwap tagged):", len(r20_trades))

# entry price: use last close (approx) -> deviation vs vwap. We have net_pnl only, use entry_date close from bars.
# Simplify: use vwap tag only (above/below vwap at entry via close)


def report(label, rs):
    if len(rs) < 100:
        print(f"{label}: n={len(rs)} (过小)"); return
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"]).startswith(y)]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== VWAP 辅助（20日滚动 VWAP 标签）===")
# deviation split needs entry price; use symbol+entry_date close as proxy via a quick lookup
dev_cache = {}
def entry_close(symbol, entry_date):
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    if fn not in dev_cache:
        p = os.path.join(KT, fn)
        if not os.path.exists(p):
            dev_cache[fn] = []
            return None
        raw = json.load(open(p, encoding="utf-8"))
        dev_cache[fn] = [(("".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]), float(r["c"])) for r in raw if r.get("t") and r.get("c")]
    ds = dev_cache[fn]
    for d, c in reversed(ds):
        if d <= str(entry_date):
            return c
    return None

for t in r20_trades:
    ec = entry_close(t["symbol"], t["entry_date"])
    if ec and t["vwap"]:
        t["dev"] = (ec - t["vwap"]) / t["vwap"]
    else:
        t["dev"] = None

report("基线（全部）", [t for t in r20_trades if t["dev"] is not None])
report("price >= VWAP（在 VWAP 上方）", [t for t in r20_trades if t["dev"] is not None and t["dev"] >= 0])
report("price < VWAP（在 VWAP 下方）", [t for t in r20_trades if t["dev"] is not None and t["dev"] < 0])
report("|dev| < 3%（VWAP 隧道内）", [t for t in r20_trades if t["dev"] is not None and abs(t["dev"]) < 0.03])
report("|dev| >= 3%（隧道外）", [t for t in r20_trades if t["dev"] is not None and abs(t["dev"]) >= 0.03])

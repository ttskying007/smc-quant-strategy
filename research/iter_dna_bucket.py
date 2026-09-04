# -*- coding: utf-8 -*-
"""Stock DNA bucketing: volatility and liquidity traits at entry (PIT).
Test if SMC TP2-R20 signal quality varies by stock DNA bucket.
Each trade tagged with: vol20 (ATR-like), liq20 (avg volume), size proxy."""
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


def dna_at(symbol, entry_date):
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    p = os.path.join(KT, fn)
    if not os.path.exists(p):
        return None
    bs = bars(p)
    dates = [b["t"] for b in bs]
    if entry_date not in dates:
        prev = [d for d in dates if d < entry_date]
        if not prev:
            return None
        i = dates.index(prev[-1])
    else:
        i = dates.index(entry_date)
    if i < 25:
        return None
    win = bs[i - 20:i]
    if not win:
        return None
    # volatility: mean(high-low)/close over 20 bars
    vol = sum((b["h"] - b["l"]) / b["c"] for b in win) / len(win)
    # liquidity: mean volume
    liq = sum(b["v"] for b in win) / len(win)
    return vol, liq


trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        r["t1_violation"] = str(r.get("t1_violation", "")).lower() in ("true", "1", "yes")
        trades.append(r)

# r20 filter
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

r20_trades = []
for t in trades:
    r20 = r20_of(t["symbol"], str(t["entry_date"]))
    if r20 is None or not (0 <= r20 < 0.15):
        continue
    dna = dna_at(t["symbol"], str(t["entry_date"]))
    if dna is None:
        continue
    t["vol20"], t["liq20"] = dna
    r20_trades.append(t)
print("TP2-R20 with DNA:", len(r20_trades))

# median splits
vols = sorted(t["vol20"] for t in r20_trades)
liqs = sorted(t["liq20"] for t in r20_trades)
vmed = vols[len(vols) // 2]
lmed = liqs[len(liqs) // 2]
print(f"vol median: {vmed:.4f}, liq median: {lmed:.0f}")


def report(label, rs):
    if len(rs) < 80:
        print(f"{label}: n={len(rs)} (过小)"); return
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"]).startswith(y)]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== 个股 DNA 分桶 ===")
report("全部", r20_trades)
report("低波动 (vol<=med)", [t for t in r20_trades if t["vol20"] <= vmed])
report("高波动 (vol>med)", [t for t in r20_trades if t["vol20"] > vmed])
report("低流动 (liq<=med)", [t for t in r20_trades if t["liq20"] <= lmed])
report("高流动 (liq>med)", [t for t in r20_trades if t["liq20"] > lmed])
report("低波动+高流动", [t for t in r20_trades if t["vol20"] <= vmed and t["liq20"] > lmed])
report("高波动+高流动", [t for t in r20_trades if t["vol20"] > vmed and t["liq20"] > lmed])

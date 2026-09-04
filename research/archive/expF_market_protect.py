# -*- coding: utf-8 -*-
"""Experiment F: extreme-market protection (forced cash when market 20d cumulative
return < threshold). Risk management rule, not timing signal.
Test thresholds -8%/-10%/-12% on R20[0,0.15) subset."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
import random
random.seed(42)
files = sorted(os.listdir(KT))[:]
sample = random.sample(files, min(500, len(files)))
# market index (equal-weight 500)
level = defaultdict(list)
for f in sample:
    raw = json.load(open(os.path.join(KT, f), encoding="utf-8"))
    prev = None
    for r in raw:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        c = float(r.get("c") or 0)
        if t and c:
            level[t].append(c)
idx = {t: sum(v) / len(v) for t, v in level.items()}
dates = sorted(idx)
# market 20d cumulative return at each date
mkt20 = {}
for i, t in enumerate(dates):
    if i >= 20:
        mkt20[t] = idx[t] / idx[dates[i - 20]] - 1
print("market 20d ret days:", len(mkt20))

trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["t1_violation"] = str(r.get("t1_violation", "")).lower() in ("true", "1", "yes")
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

# recompute r20
cache = {}
def r20_of(symbol, entry_date):
    if symbol not in cache:
        p = os.path.join(KT, symbol.replace(".", "_") + "_daily_800.json")
        if not os.path.exists(p):
            cache[symbol] = []
            return None
        raw = json.load(open(p, encoding="utf-8"))
        closes = [(("".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]), float(r["c"])) for r in raw if r.get("t") and r.get("c")]
        closes.sort()
        cache[symbol] = closes
    closes = cache[symbol]
    ds = [c[0] for c in closes]
    if entry_date not in ds:
        prev = [d for d in ds if d < entry_date]
        if not prev:
            return None
        i = ds.index(prev[-1])
    else:
        i = ds.index(entry_date) - 1
    if i < 20:
        return None
    return closes[i][1] / closes[i - 20][1] - 1

def mkt_at(entry_date):
    prev = [d for d in dates if d < entry_date]
    if not prev:
        return None
    return mkt20.get(prev[-1])

for t in trades:
    t["r20"] = r20_of(t["symbol"], str(t["entry_date"]))
    t["mkt20"] = mkt_at(t["entry_date"])
    t["year"] = str(t["entry_date"])[:4]

base = [t for t in trades if t["r20"] is not None and 0 <= t["r20"] < 0.15]
print(f"\nR20[0,0.15) 基线: n={len(base)}")

for th in (None, -0.08, -0.10, -0.12, -0.15):
    if th is None:
        rs = base
        label = "无保护"
    else:
        rs = [t for t in base if (t["mkt20"] or 0) >= th]
        label = f"市场20日<-{abs(th)*100:.0f}% 强制空仓"
    if len(rs) < 200:
        print(f"  {label}: n={len(rs)} (过小)")
        continue
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"  {label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"      {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")

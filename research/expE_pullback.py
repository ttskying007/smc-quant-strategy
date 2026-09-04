# -*- coding: utf-8 -*-
"""Experiment E: SMC oversold-reversal signal (bear-market alpha).
Idea: in downtrends, SMC demand-side reversal (deep pullback + SSL sweep + reclaim)
may work where continuation fails. Test: TP2 trades tagged by prior 20-day change;
does deep-pullback subset hold up in 2026?"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["t1_violation"] = str(r.get("t1_violation", "")).lower() in ("true", "1", "yes")
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

# tag each trade with prior 20-day change of its stock (entry-1 close vs 21 bars earlier)
def prior_ret(symbol, entry_date):
    p = os.path.join(KT, symbol.replace(".", "_") + "_daily_800.json")
    if not os.path.exists(p):
        return None
    raw = json.load(open(p, encoding="utf-8"))
    closes = []
    for r in raw:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("c"):
            closes.append((t, float(r["c"])))
    closes.sort()
    dates = [c[0] for c in closes]
    if entry_date not in dates:
        prev = [d for d in dates if d < entry_date]
        if not prev:
            return None
        i = dates.index(prev[-1])
    else:
        i = dates.index(entry_date) - 1
    if i < 20:
        return None
    return closes[i][1] / closes[i - 20][1] - 1

for t in trades:
    t["r20"] = prior_ret(t["symbol"], str(t["entry_date"]))
    t["year"] = str(t["entry_date"])[:4]

def report(label, rs):
    if len(rs) < 200:
        print(f"  {label}: n={len(rs)} (过小)"); return
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"  {label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            w = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"      {y}: n={len(ys)} WR={100*w/len(ys):.1f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.3f}%")

print("=== 按入场前 20 日涨跌幅分组 ===")
report("全部", trades)
report("r20 < -10%（深回调）", [t for t in trades if (t["r20"] or 0) < -0.10])
report("-10% <= r20 < 0（回调）", [t for t in trades if (t["r20"] or 0) >= -0.10 and (t["r20"] or 0) < 0])
report("0 <= r20 < 10%（上涨）", [t for t in trades if (t["r20"] or 0) >= 0 and (t["r20"] or 0) < 0.10])
report("r20 >= 10%（强势）", [t for t in trades if (t["r20"] or 0) >= 0.10])

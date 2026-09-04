# -*- coding: utf-8 -*-
"""Backtest check: how did 2026-08-13/14/17 entry trades (matching paper holdings)
perform in backtest - early days vs 15d? Is -4.9% normal early drawdown?"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}

# backtest event trades (v18) with entry dates in 2026-08
trades = []
with open(r"E:\test\smc_project\research\combo_v18_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        if r.get("src") == "EVENT" and str(r.get("entry_date", "")).startswith("202608"):
            trades.append(r)
print(f"回测 2026-08 事件交易: {len(trades)}")

# for each trade, forward pnl at 1/2/5/10/15 days from entry open
def bars_of(code):
    p = code2file.get(code)
    if not p:
        return None
    raw = json.load(open(p, encoding="utf-8"))
    bs = []
    for x in raw:
        t = "".join(c for c in str(x.get("t") or "") if c.isdigit())[:8]
        if t and x.get("o") and x.get("c"):
            bs.append({"t": t, "o": float(x["o"]), "c": float(x["c"])})
    bs.sort(key=lambda b: b["t"])
    return bs

by_entry = defaultdict(list)
for t in trades:
    code = str(t.get("symbol", "")).split(".")[0]
    ed = str(t.get("entry_date", ""))
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if ed not in dates:
        continue
    i = dates.index(ed)
    if i + 15 >= len(bs):
        continue
    ep = bs[i]["o"]
    if ep <= 0:
        continue
    pnls = {}
    for h in (1, 2, 5, 10, 15):
        pnls[h] = (bs[i + h]["c"] / ep - 1) * 100
    by_entry[ed].append(pnls)

for ed in sorted(by_entry):
    rs = by_entry[ed]
    n = len(rs)
    avg1 = sum(r[1] for r in rs) / n
    avg2 = sum(r[2] for r in rs) / n
    avg5 = sum(r[5] for r in rs) / n
    avg15 = sum(r[15] for r in rs) / n
    print(f"入场 {ed}: n={n} | 1日 {avg1:+.2f}% | 2日 {avg2:+.2f}% | 5日 {avg5:+.2f}% | 15日 {avg15:+.2f}%")

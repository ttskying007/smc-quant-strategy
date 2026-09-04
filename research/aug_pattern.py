# -*- coding: utf-8 -*-
"""Historical August pattern: in backtest, do event trades entered in August
show early (1-2d) drawdown before 15d gain? Compare 2024-08 / 2025-08."""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}

trades = []
with open(r"E:\test\smc_project\research\combo_v18_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        if r.get("src") == "EVENT":
            trades.append(r)

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

# August entries by year
by_year_month = defaultdict(lambda: defaultdict(list))
for t in trades:
    ed = str(t.get("entry_date", ""))
    if ed[4:6] != "08":
        continue
    code = str(t.get("symbol", "")).split(".")[0]
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
    pnls = {h: (bs[i + h]["c"] / ep - 1) * 100 for h in (1, 2, 5, 15)}
    by_year_month[ed[:4]][ed].append(pnls)

print("=== 历史 8 月事件交易（回测）===")
for year in ("2023", "2024", "2025"):
    entries = by_year_month.get(year, {})
    if not entries:
        continue
    all1 = []
    all2 = []
    all15 = []
    for ed, rs in entries.items():
        n = len(rs)
        all1 += [r[1] for r in rs]
        all2 += [r[2] for r in rs]
        all15 += [r[15] for r in rs]
    avg1 = sum(all1) / len(all1)
    avg2 = sum(all2) / len(all2)
    avg15 = sum(all15) / len(all15)
    neg1 = sum(1 for x in all1 if x < 0) / len(all1) * 100
    print(f"  {year}-08: n={len(all1)} | 1日 {avg1:+.2f}% (负占比{neg1:.0f}%) | 2日 {avg2:+.2f}% | 15日 {avg15:+.2f}%")

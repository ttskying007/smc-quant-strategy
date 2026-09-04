# -*- coding: utf-8 -*-
"""Analyze 8-19 paper loss structure: which event types underperformed?
Buyback vs increase, DEEP vs non-DEEP (from ledger priority), high vs low vol."""
import json, io, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))

# tag each holding: return 8-18->8-19, title type (buyback vs increase)
recs = []
for t in led:
    code = t["code"]
    ex = "SH" if code.startswith("6") else "SZ"
    p = os.path.join(KT, f"{code}_{ex}_daily_800.json")
    if not os.path.exists(p):
        continue
    raw = json.load(open(p, encoding="utf-8"))
    dates = [b["t"] for b in raw]
    if "20260818" not in dates or "20260819" not in dates:
        continue
    i = dates.index("20260818")
    c18 = raw[i]["c"]
    c19 = raw[i + 1]["c"]
    if c18 <= 0:
        continue
    title = str(t.get("name", "")) + ":" + str(t.get("source", ""))
    is_buyback = "回购" in str(t.get("title", ""))
    recs.append({"code": code, "ret": (c19 / c18 - 1) * 100, "is_buyback": is_buyback,
                 "priority": t.get("priority", "STD"), "title": str(t.get("title", ""))[:30]})

print(f"分析持仓: {len(recs)} 只")
# by type
by_type = defaultdict(list)
for r in recs:
    by_type["回购" if r["is_buyback"] else "增持"].append(r["ret"])
for k, v in by_type.items():
    print(f"  {k}: n={len(v)} avg={sum(v)/len(v):+.2f}%")
# by priority
by_pri = defaultdict(list)
for r in recs:
    by_pri[r["priority"]].append(r["ret"])
for k, v in by_pri.items():
    print(f"  priority={k}: n={len(v)} avg={sum(v)/len(v):+.2f}%")

# top losers
recs.sort(key=lambda r: r["ret"])
print("\n最差 5 只:")
for r in recs[:5]:
    print(f"  {r['code']} {r['ret']:+.1f}% {r['title']}")
print("最好 5 只:")
for r in recs[-5:]:
    print(f"  {r['code']} {r['ret']:+.1f}% {r['title']}")

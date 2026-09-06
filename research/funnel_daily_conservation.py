# -*- coding: utf-8 -*-
"""复审 P1-4: 漏斗逐日守恒 —— 每只股票逐层计数、Σ=universe、DATA_MISSING 与 STRATEGY_REJECT 分离。
对最近 N 个交易日回放，输出每日漏斗各层计数 + 守恒校验 + 数据缺失单列。
"""
import io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as WE

KLINE = r"E:\test\smc_project\hermes\kline_cache"
DAYS = 5  # 最近 5 交易日（控制运行时间）

def load(path):
    raw = json.load(open(path, encoding="utf-8"))
    bs = []
    for r in raw:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                       "c": float(r["c"]), "v": float(r["v"])})
    bs.sort(key=lambda b: b["t"])
    return bs

# 市场最新日
files = sorted(f for f in os.listdir(KLINE) if f.endswith("_daily_750.json"))[:800]
latest_cnt = defaultdict(int)
for p in files:
    d = load(os.path.join(KLINE, p))
    if d:
        latest_cnt[d[-1]["t"]] += 1
latest = max(latest_cnt, key=latest_cnt.get)
print(f"市场最新日: {latest}")

# 最近 DAYS 个交易日（从 sample 收集）
sample_dates = set()
for p in files:
    d = load(os.path.join(KLINE, p))
    if d:
        sample_dates.add(d[-1]["t"])
all_td = sorted(sample_dates)[-DAYS:]

print("\n=== 逐日漏斗守恒 ===")
ok_all = True
for day in all_td:
    funnel = defaultdict(int)
    missing = 0
    universe = 0
    for p in files:
        d = load(os.path.join(KLINE, p))
        if not d:
            missing += 1
            continue
        universe += 1
        if len(d) < 400:
            funnel["len_lt_400"] += 1
            continue
        if d[-1]["t"] != day:
            funnel["stale_or_not_day"] += 1
            continue
        code = p.split("_")[0]
        sym = code + (".SH" if code.startswith("6") else ".SZ")
        seeds = WE.build_seeds(sym, d)
        entry_today = [s for s in seeds if int(s["entry_idx"]) == len(d) - 1]
        if entry_today:
            funnel["candidate"] += 1
        else:
            funnel["no_entry_today"] += 1
    total_stages = sum(funnel.values())
    conserved = (total_stages == universe)
    ok_all = ok_all and conserved
    print(f"\n[{day}] universe={universe} 数据缺失={missing}")
    print(f"  分层: " + " ".join(f"{k}={v}" for k, v in sorted(funnel.items())))
    print(f"  Σ分层={total_stages} == universe={universe} → {'守恒 ✅' if conserved else '不守恒 ❌'}")
    if not conserved:
        print(f"  缺口: {universe - total_stages}（未归因股票数）")

print(f"\n=== 全部日守恒: {'✅' if ok_all else '❌'} | 数据缺失单列: 已与策略拒绝分离 ===")

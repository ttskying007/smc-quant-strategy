# -*- coding: utf-8 -*-
"""E1: Structure Engine 每日 Funnel artifact(第三轮深审) —— V3升级版
V3 Phase B 要求: 每层不只记 count, 还要记【丢失候选的前向收益】—— 回答
"系统在哪里杀掉了最多机会"(被杀的候选后来涨没涨)。
层: universe → pool → sweep → reclaim → disp → shift → poi → retest(READY)
每层额外: 丢失候选样本(下一层未通过的) 的 5D/10D 前向收益(决策点次日起)。
输出: handover/structure_funnel_daily.json(滚动30天)。
"""
import glob, io, json, os, sys, time
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.liquidity as LQ
import core.displacement as DS
import core.mss as MSS
import core.fvg_ob as FO
from core.sequence import run_sequence_v2

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OUT = r"E:\test\smc_project\research\handover\structure_funnel_daily.json"
SAMPLE_STRIDE = 10        # 全量太慢: 每10只抽1(研究监测口径)
RECENT_BARS = 30          # 只扫最近30根(每日增量)

files = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::SAMPLE_STRIDE]
funnel = defaultdict(int)
lost_ret = defaultdict(list)     # V3 Phase B: 各层丢失候选的前向收益(5D/10D)
today = time.strftime("%Y%m%d")

def fwd_ret(daily, i, days):
    """决策点 i 的 days 日前向收益(次日起)。数据不足 → None。"""
    n = len(daily)
    if i + 1 + days >= n:
        return None
    base = daily[i + 1]["o"]
    return round((daily[min(n - 1, i + 1 + days)]["c"] / base - 1) * 100, 3) if base else None

for fp in files:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    if len(raw) < 200:
        continue
    daily = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
              "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    funnel["universe"] += 1
    code = os.path.basename(fp).split("_")[0]
    n = len(daily)
    for i in range(max(150, n - RECENT_BARS), n):
        try:
            m = run_sequence_v2(daily, i, symbol=code)
        except Exception:
            funnel["error"] += 1
            continue
        funnel["bars_scanned"] += 1
        kinds = {e["event_type"] for e in m.events}
        reached = ["LIQUIDITY", "SWEEP", "RECLAIM", "DISPLACEMENT", "SHIFT", "POI", "RETEST"]
        deepest = 0
        for li, ev in enumerate(reached):
            if ev in kinds:
                funnel[f"L{li+1}_{ev.lower()}"] += 1
                deepest = li + 1
        # V3 Phase B: 每个断层的丢失候选前向收益(到达层 Lk 但未到 Lk+1 的 bar)
        for li in range(len(reached) - 1):
            if deepest == li:      # 链停在 L(li+1), 丢失在下一层
                r5, r10 = fwd_ret(daily, i, 5), fwd_ret(daily, i, 10)
                if r5 is not None:
                    lost_ret[f"L{li+2}_lost_fwd5"].append(r5)
                if r10 is not None:
                    lost_ret[f"L{li+2}_lost_fwd10"].append(r10)
        if m.rejected:
            funnel["reject_" + m.rejected[0]["why"]] += 1

layers = ["universe", "bars_scanned", "L1_liquidity", "L2_sweep", "L3_reclaim",
          "L4_displacement", "L5_shift", "L6_poi", "L7_retest"]
entry = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "sample": len(files),
         "funnel": {k: funnel[k] for k in layers},
         "drop_reasons": {k: v for k, v in funnel.items() if k.startswith("reject_")},
         "lost_candidate_forward_return": {                      # V3 Phase B
             k: {"n": len(v), "avg": round(sum(v) / len(v), 3),
                 "median": round(sorted(v)[len(v) // 2], 3), "pct_pos": round(len([x for x in v if x > 0]) / len(v) * 100, 1)}
             for k, v in lost_ret.items() if v},
         "ready_per_day": funnel["L7_retest"]}

# 滚动历史(30天)
hist = []
if os.path.exists(OUT):
    try:
        old = json.load(open(OUT, encoding="utf-8"))
        hist = old.get("history", [])
        if hist and hist[-1].get("generated_at", "")[:10] == entry["generated_at"][:10]:
            hist = hist[:-1]  # 当日覆盖
    except Exception:
        hist = []
hist.append(entry)
hist = hist[-30:]
json.dump({"latest": entry, "history": hist}, open(OUT, "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

print(f"== 结构引擎每日 Funnel({len(files)}股抽样×{RECENT_BARS}bar) ==")
for k in layers:
    print(f"  {k:16s}: {funnel[k]}")
print("  拒因:", dict(entry["drop_reasons"]))
print(f"READY: {funnel['L7_retest']} → 已写 {OUT}")
print("丢失候选前向收益(V3 Phase B):")
for k, v in entry.get("lost_candidate_forward_return", {}).items():
    print(f"  {k}: n={v['n']} avg={v['avg']}% pos={v['pct_pos']}%")
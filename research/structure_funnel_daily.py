# -*- coding: utf-8 -*-
"""E1: Structure Engine 每日 Funnel artifact(第三轮深审)
每日(或回补指定日)用完整链引擎(run_sequence_v2)扫描全市场抽样,
输出每层 input/output/pass_rate/drop_reason —— 第三轮深审 E1 验收:
'任何一天 BUY=0 都能解释' 在结构引擎层同样成立。
输出: handover/structure_funnel_daily.json(滚动保留 30 天历史)。
层: universe → pool → sweep → reclaim → disp → shift → poi → retest(READY)
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
today = time.strftime("%Y%m%d")

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
        # 只统计最近窗口; 每 bar 尝试完整链(诊断哪层断)
        try:
            m = run_sequence_v2(daily, i, symbol=code)
        except Exception:
            funnel["error"] += 1
            continue
        funnel["bars_scanned"] += 1
        kinds = {e["event_type"] for e in m.events}
        for layer, ev in (("L1_pool", "LIQUIDITY"), ("L2_sweep", "SWEEP"), ("L3_reclaim", "RECLAIM"),
                          ("L4_disp", "DISPLACEMENT"), ("L5_shift", "SHIFT"), ("L6_poi", "POI"),
                          ("L7_retest_ready", "RETEST")):
            if ev in kinds:
                funnel[layer] += 1
        if m.rejected:
            funnel["reject_" + m.rejected[0]["why"]] += 1

layers = ["universe", "bars_scanned", "L1_pool", "L2_sweep", "L3_reclaim", "L4_disp",
          "L5_shift", "L6_poi", "L7_retest_ready"]
entry = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "sample": len(files),
         "funnel": {k: funnel[k] for k in layers},
         "drop_reasons": {k: v for k, v in funnel.items() if k.startswith("reject_")},
         "ready_per_day": funnel["L7_retest_ready"]}

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
print(f"READY: {funnel['L7_retest_ready']} → 已写 {OUT}")
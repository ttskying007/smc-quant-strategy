# -*- coding: utf-8 -*-
"""V2 ITERATION 1(前置)/2e: 全市场 Structure Engine Funnel 审计
蓝图 §14/§56-57: 为什么股票少? 用新引擎(无 R20/Stage/FVG-hard 硬门槛)跑全市场,
量化每层 pass/reject —— 与生产 wdh 引擎(带硬门槛)对比, 分离'市场无机会'与'门槛杀人'。

Funnel 层(新引擎, 决策时点 i, 无前视):
  L0 universe(K线≥400)
  L1 流动性池存在(score>=40 SSL)
  L2 扫损(bar.low 破池后收回)
  L3 收回(reclaim 关键位)
  L4 位移(displacement score>=50)
  L5 结构转移(CHOCH/BOS via core/mss)
  L6 POI(FVG 或 OB)
  L7 重测(RETEST: 价格回到 POI 区)
  → READY(相当于旧引擎的 BUY 候选)
对比臂: 生产 wdh 种子(带全部硬门槛)同期数量。
"""
import csv, io, json, os, sys, glob
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.liquidity as LQ
import core.displacement as DS
import core.mss as MSS
import core.fvg_ob as FO

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
# 抽样 800 只(全市场 4662 太慢, 抽样已够量化层级衰减; 用与生产同 K 线缓存)
files = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::5][:800]  # 每5只取1

funnel = defaultdict(int)
samples = defaultdict(list)
ready_trades = []  # (code, date, state签名)

for fp in files:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    code = os.path.basename(fp).split("_")[0]
    if len(raw) < 150:
        continue
    daily = [{"t": str(b.get("t") or b.get("date") or "")[:8], "o": float(b["o"]), "h": float(b["h"]),
              "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    funnel["L0_universe"] += 1
    # 扫描最近 400 根(决策点从 i=150 起, 只统计近 OOS 期 2025-07 后的信号 → 用日期过滤)
    n = len(daily)
    sm_state_by_start = {}
    for i in range(150, n):
        d8 = daily[i]["t"]
        if d8 < "20250701":
            continue  # 只统计 OOS 期(同生产对比窗)
        # ---- 每层独立计数(按 bar 决策点) ----
        funnel["bars_scanned"] += 1
        pools = LQ.liquidity_pools(daily, i)
        ssl = [p for p in pools if p["side"] == "SSL" and p["score"] >= 40]
        if ssl:
            funnel["L1_pool"] += 1
            # L2 扫损: 本bar破池后收回
            b = daily[i]
            pool = ssl[0]["price"]
            atr_pct = 0.02
            try:
                from core.structure import atr_of
                a_ = atr_of(daily, i - 1)
                if a_:
                    atr_pct = a_ / (daily[i-1]["c"] or 1)
            except Exception:
                pass
            tol = max(0.003, atr_pct * 0.5)
            if b["l"] <= pool * (1 - tol) and b["c"] > pool:
                funnel["L2_sweep"] += 1
                # L3 收回: 5根内收复本bar高点上方前高
                ph = max(x["h"] for x in daily[max(0, i-5):i]) if i >= 5 else b["h"]
                for k in range(i + 1, min(n, i + 6)):
                    if daily[k]["c"] > ph:
                        funnel["L3_reclaim"] += 1
                        # L4 位移(收回根)
                        sc = DS.displacement_score(daily, k)
                        if sc["score"] >= 50:
                            funnel["L4_disp"] += 1
                            # L5 结构转移(收回后 12 根内)
                            for m in range(k, min(n, k + 13)):
                                s5 = MSS.structure_shift(daily, m)
                                if s5 and s5["direction"] == "LONG":
                                    funnel["L5_shift"] += 1
                                    # L6 POI(FVG 或 OB)
                                    f6 = FO.fvg_at(daily, m)
                                    ob6 = FO.order_block(daily, m, "BULL")
                                    if f6 or ob6:
                                        funnel["L6_poi"] += 1
                                        poi = f6 if f6 else ob6
                                        # L7 重测: POI 后 10 根内回到区间
                                        lo_, hi_ = poi["low"], poi["high"]
                                        for q in range(m + 1, min(n, m + 11)):
                                            if lo_ <= daily[q]["l"] <= hi_ * 1.02:
                                                funnel["L7_retest"] += 1
                                                ready_trades.append((code, daily[q]["t"],
                                                                      "pool→sweep→reclaim→disp→shift→poi→retest"))
                                                break
                                            if daily[q]["c"] < lo_ * 0.97:
                                                break
                                    break
                            break
                    elif daily[k]["c"] < pool * (1 - 2 * tol):
                        break  # 失效
# 汇总
res = {"asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
       "sample": {"files": len(files), "oos_from": OOS},
       "funnel": dict(funnel),
       "ready_count": len(ready_trades),
       "ready_per_month": round(len(ready_trades) / 13, 1),  # 2025-07~2026-08 约13个月
       "sample_ready": ready_trades[:20]}
print("== 新引擎全市场 Funnel(800股抽样, OOS期13个月) ==")
order = ["bars_scanned", "L0_universe", "L1_pool", "L2_sweep", "L3_reclaim", "L4_disp", "L5_shift", "L6_poi", "L7_retest"]
for k in order:
    print(f"  {k:14s}: {funnel[k]}")
if funnel["L2_sweep"]:
    print("\n转化率:")
    prev = funnel["bars_scanned"]
    for k in order[2:]:
        r_ = funnel[k] / max(1, prev)
        print(f"  {k:12s}/{prev}: {r_:.3%}")
        prev = funnel[k]
print(f"\nREADY(链完整): {len(ready_trades)} 笔 (~{len(ready_trades)/13:.1f}/月)")
print("\n样例:")
for t in ready_trades[:6]:
    print("  ", t)
# 对比: 生产 wdh 种子同期数量
try:
    seeds = list(csv.DictReader(open(r"E:\test\smc_project\wdh\W1D1D4_seeds.csv", encoding="utf-8-sig")))
    oos_seeds = [s for s in seeds if str(s.get("entry_date") or "") >= "20250701"]
    print(f"\n生产wdh种子(带全部硬门槛) OOS期: {len(oos_seeds)} (~{len(oos_seeds)/13:.1f}/月)")
    res["wdh_oos_seeds"] = len(oos_seeds)
except Exception as e:
    print("wdh对照读取失败:", e)

json.dump(res, open(r"E:\test\smc_project\research\handover\V2全市场Funnel审计.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("\n已写 handover/V2全市场Funnel审计.json")
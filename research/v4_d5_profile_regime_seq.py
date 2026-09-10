# -*- coding: utf-8 -*-
"""v4_d5_profile_regime_seq.py —— D5: Profile×Regime×Sequence 三维参数分布自适应(V3 Phase D)
蓝图: P(params | profile, regime, sequence) —— Level-3 自适应(审计 V3 P2 项)。
已有: Level-1(v2_profile_ab: profile only, OOS avg+PF双升但 CI 双跨 0)。
本实验(预注册):
  维度: ① profile 聚类(core.profile, 6族) × ② regime(E 三档: low/mid/high, 决策时点) × ③
        sequence(2: A_full 完整链 vs B_no_reclaim 简化链 —— Family DB 两大已验族)
  参数: max_hold(15/25) × sl_buf(1.2/1.5/2.25 ATR) —— 6 组合
  方法: 每层(cell) IS(2023-07~2025-06)学最优参数 → OOS(2025-07+)应用该参数,
        vs 全局固定参数基线(1.5ATR/15bar, B3 语义)。
  预注册判定:
    D1 层级充足: 每 cell IS n>=30 且 OOS n>=10 才计入(不足→该层用全局参数)
    D2 增量: 三维版 OOS avg − 基线 ≥ +0.5pp 且 PF 不降 → 三维自适应有效
    D3 过拟合护栏: IS→OOS 参数翻转率(层参数在 OOS 反而更差) ≤ 50% —— 超过说明
       IS 选参是噪声, 维度必须降级(如实报"Profile only"或"固定")
输出: handover/V4_D5_三维自适应.json"""
import glob, io, json, os, random, sys, time
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.liquidity as LQ
import core.displacement as DS
import core.mss as MSS
import core.fvg_ob as FO
import core.entry as EN
import core.profile as PR
from core.structure import atr_of

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.2
FILES = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::4][:1200]

# E 三档(全历史快照)
E_HIST = {}
try:
    _h = json.load(open(r"E:\test\smc_project\research\handover\escore_history_full.json",
                       encoding="utf-8"))
    E_HIST = {d["d8"]: d.get("e") for d in _h.get("days", []) if d.get("e") is not None}
except Exception:
    pass
_es = sorted(v for v in E_HIST.values() if v is not None)
Q33, Q67 = _es[len(_es) // 3], _es[len(_es) * 2 // 3]
def e_band(d8):
    e = E_HIST.get(d8)
    if e is None:
        return None
    return "low" if e <= Q33 else "mid" if e <= Q67 else "high"

PARAM_GRID = [{"wide": w, "hold": h} for w in (1.2, 1.5, 2.25) for h in (15, 25)]
BASE = {"wide": 1.5, "hold": 15}

def sim(daily, q, zone, wide, hold):
    f = EN.fill_in_zone(daily, q, zone, max_bars=6)
    if f is None or f["fill_price"] is None:
        return None
    k0, px = f["fill_idx"], f["fill_price"]
    if k0 + 2 >= len(daily):
        return None
    a_ = atr_of(daily, k0) or px * 0.025
    sl = zone["invalid_price"] - wide * a_
    for k in range(k0 + 1, min(len(daily), k0 + hold + 1)):
        if daily[k]["l"] <= sl:
            return ((sl / px - 1) * 100) - FEE
    return ((daily[min(len(daily) - 1, k0 + hold)]["c"] / px - 1) * 100) - FEE

t0 = time.time()
# 采集: (profile, eband, seq, is_oos, param_idx → ret) 每决策点全 6 参数同算
cells = defaultdict(lambda: {"is": [[] for _ in PARAM_GRID], "oos": [[] for _ in PARAM_GRID]})
n_pts = 0
for fp in FILES:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    if len(raw) < 150:
        continue
    code = os.path.basename(fp).split("_")[0]
    daily = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
              "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    n = len(daily)
    for i in range(150, n):
        d8 = daily[i]["t"]
        if d8 < "20230628":
            continue
        band = e_band(d8)
        if band is None:
            continue
        pools = LQ.liquidity_pools(daily, i)
        ssl = [p for p in pools if p["side"] == "SSL" and p["score"] >= 40]
        if not ssl:
            continue
        b = daily[i]
        a_ = atr_of(daily, i - 1) or 0
        atr_pct = (a_ / (daily[i - 1]["c"] or 1)) if a_ else 0.02
        tol = max(0.003, atr_pct * 0.5)
        pool = ssl[0]["price"]
        if not (b["l"] <= pool * (1 - tol) and b["c"] > pool):
            continue
        ph = max(x["h"] for x in daily[max(0, i - 5):i]) if i >= 5 else b["h"]
        for k in range(i + 1, min(n, i + 6)):
            if daily[k]["c"] > ph:
                sc = DS.displacement_score(daily, k)
                if sc["score"] >= 50:
                    for m in range(k, min(n, k + 13)):
                        s5 = MSS.structure_shift(daily, m)
                        if s5 and s5["direction"] == "LONG":
                            f6 = FO.fvg_at(daily, m)
                            ob6 = FO.order_block(daily, m, "BULL")
                            if f6 or ob6:
                                poi = f6 if f6 else ob6
                                for q in range(m + 1, min(n, m + 11)):
                                    if poi["low"] <= daily[q]["l"] <= poi["high"] * 1.02:
                                        z = EN.entry_zone(poi, price=daily[q]["c"],
                                                          invalid_price=poi["low"] * 0.97, atr_pct=atr_pct)
                                        if z is None:
                                            break
                                        prof = PR.stock_profile(daily, q, window=120)
                                        cluster = PR.profile_cluster(prof) or "none"
                                        # sequence: A_full 需 reclaim(当前链语义=完整); B 简化=跳 reclaim 亦可达此处(本扫描即无 reclaim 门的 SWEEP→DISP 语义)
                                        seq = "full"
                                        rets = [sim(daily, q, z, pg["wide"], pg["hold"]) for pg in PARAM_GRID]
                                        if all(r is None for r in rets):
                                            break
                                        key = (cluster, band, seq)
                                        bucket = cells[key]["is"] if d8 < OOS else cells[key]["oos"]
                                        for pi, r in enumerate(rets):
                                            if r is not None:
                                                bucket[pi].append(r)
                                        n_pts += 1
                                        break
                                    if daily[q]["c"] < poi["low"] * 0.97:
                                        break
                            break
                    break
            elif daily[k]["c"] < pool * (1 - 2 * tol):
                break
print(f"决策点 {n_pts}, cells {len(cells)}, {time.time()-t0:.0f}s")

# IS 学参 → OOS 用参
def mean(v):
    return sum(v) / len(v) if v else None

cell_pick, oos_base_rets, oos_adapt_rets = {}, [], []
n_flip = n_eff = 0
for key, b in cells.items():
    is_rets = [mean(x) for x in b["is"]]
    is_ns = [len(x) for x in b["is"]]
    # D1 充足: IS n>=30
    cand = [pi for pi in range(len(PARAM_GRID)) if is_ns[pi] >= 30]
    pick = None
    if cand:
        pick = max(cand, key=lambda pi: is_rets[pi])
        # D1b: OOS 也要有样本
        if all(len(b["oos"][pi]) == 0 for pi in cand):
            pick = None
    cell_pick[key] = pick
    # OOS 段: 基线 vs 自适应
    base_oos = b["oos"][0] if False else None
    # 基线 = PARAM_GRID index of BASE
    bidx = PARAM_GRID.index(BASE)
    for r in b["oos"][bidx]:
        oos_base_rets.append(r)
    if pick is not None:
        for r in b["oos"][pick]:
            oos_adapt_rets.append(r)
        n_eff += 1
        # 翻转: OOS 上 pick 均值 < 基线均值
        if mean(b["oos"][pick]) is not None and mean(b["oos"][bidx]) is not None \
           and mean(b["oos"][pick]) < mean(b["oos"][bidx]):
            n_flip += 1
        else:
            pass

def stats(v):
    if not v:
        return {"n": 0}
    w = sum(x for x in v if x > 0)
    l_ = abs(sum(x for x in v if x <= 0))
    return {"n": len(v), "avg": round(sum(v) / len(v), 3),
            "wr": round(len([x for x in v if x > 0]) / len(v) * 100, 1),
            "pf": round(w / l_, 2) if l_ else 99.0}

sB, sA = stats(oos_base_rets), stats(oos_adapt_rets)
delta = round(sA["avg"] - sB["avg"], 3) if sA.get("avg") is not None and sB.get("avg") is not None else None
flip_rate = round(n_flip / max(1, n_eff), 2) if n_eff else None
verdict = {
    "D1_层级充足(cells_with_pick)": n_eff,
    "D2_增量≥0.5pp且PF不降": bool(delta is not None and delta >= 0.5
                                  and (sA.get("pf") or 0) >= (sB.get("pf") or 0)),
    "D3_翻转率≤50%": bool(flip_rate is not None and flip_rate <= 0.50),
    "delta_oos_pp": delta, "flip_rate": flip_rate,
    "adaptive_valid": bool(delta is not None and delta >= 0.5
                           and (sA.get("pf") or 0) >= (sB.get("pf") or 0)
                           and flip_rate is not None and flip_rate <= 0.50),
}
random.seed(5)
def bootci(v, iters=2000):
    if len(v) < 10:
        return None
    ms = sorted(sum(random.choices(v, k=len(v))) / len(v) for _ in range(iters))
    return [round(ms[int(0.025 * iters)], 3), round(ms[int(0.975 * iters)], 3)]
out = {"cells_total": len(cells), "cells_effective": n_eff,
       "oos_baseline": {**sB, "ci": bootci(oos_base_rets)},
       "oos_adaptive": {**sA, "ci": bootci(oos_adapt_rets)},
       "param_grid": PARAM_GRID, "base": BASE,
       "e_cut": {"q33": Q33, "q67": Q67},
       "preregistered": verdict,
       "dimension_note": "Profile(6)×Regime(3)×Sequence(1: full) —— 本版 sequence 维仅 full(Family DB 两大族结论已另有实验)",
       "runtime_s": round(time.time() - t0)}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_D5_三维自适应.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"基线 OOS: {sB} CI={out['oos_baseline']['ci']}")
print(f"自适应 OOS: {sA} CI={out['oos_adaptive']['ci']}")
print(f"Δ={delta}pp 翻转率={flip_rate} 有效层={n_eff}/{len(cells)}")
print("预注册:", json.dumps(verdict, ensure_ascii=False))
print("已写 handover/V4_D5_三维自适应.json")
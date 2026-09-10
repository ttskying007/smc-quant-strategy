# -*- coding: utf-8 -*-
"""E5: Parameter Surface 实验(第三轮深审 E5)
深审 §77: 参数不要单点, 看曲面。理想=邻域整体可用, 危险=只有单点最优。
本实验: 完整链引擎的两个上游参数 ——
  pivot(结构摆动确认半径, 2/3/4/5) × sweep_tol(ATR×系数, 0.3/0.5/0.8/1.0)
产出 OOS avg/PF/READY数 三指标曲面。判定:
  平面稳定(相邻格差不剧烈, 最优不在边缘) → 参数可信;
  单点尖峰(邻格全差) → 过拟合警报。
只读实验, 不动生产。"""
import glob, io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.liquidity as LQ
import core.displacement as DS
import core.mss as MSS
import core.fvg_ob as FO
import core.structure as ST
from core.entry import fill_in_zone
from core.sequence import run_sequence_v2

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.20
PIVOTS = (2, 3, 4, 5)
TOLS = (0.3, 0.5, 0.8, 1.0)   # sweep_tol = tol系数×ATR%

# 预载K线(一次)
FILES = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::5][:400]  # 400股×16格已够曲面形状
DAILY = {}
for fp in FILES:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    if len(raw) < 200:
        continue
    code = os.path.basename(fp).split("_")[0]
    DAILY[code] = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
                    "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]

def run_cell(pivot, tol_mult):
    """一格: 全链扫描 → READY 回测(B3退出)。
    pivot = liquidity 模块的 swing 确认半径(模块级常量 PIVOT_R) —— 单格临时替换。"""
    import core.liquidity as LQx
    import core.displacement as DSx
    import core.fvg_ob as FOx
    _orig_pivot = LQx.PIVOT_R
    LQx.PIVOT_R = pivot
    pnl = []
    ready = 0
    for code, daily in DAILY.items():
        n = len(daily)
        for i in range(150, n - 20):
            if daily[i]["t"] < OOS:
                continue
            # 手动链(支持 tol_mult): 池→扫(tol_mult)→收复→位移→转移→POI→重测
            pools = LQx.liquidity_pools(daily, i)
            ssl = [p for p in pools if p["side"] == "SSL" and p["score"] >= 40]
            if not ssl:
                continue
            pool = ssl[0]
            a_ = ST.atr_of(daily, i - 1) or 0
            atr_pct = a_ / (daily[i-1]["c"] or 1) if a_ else 0.02
            tol = max(0.003, atr_pct * tol_mult)
            # 扫损在近 12 bar 内任意根
            sw_i = None
            for k in range(max(1, i - 12), i + 1):
                b = daily[k]
                if b["l"] <= pool["price"] * (1 - tol) and b["c"] > pool["price"]:
                    sw_i = k
                    break
            if sw_i is None:
                continue
            ph = max(x["h"] for x in daily[max(0, sw_i - 5):sw_i])
            rc_i = None
            for k in range(sw_i + 1, min(n, sw_i + 6)):
                if daily[k]["c"] > ph:
                    rc_i = k
                    break
            if rc_i is None:
                continue
            sc = None
            for k in range(rc_i, min(n, rc_i + 6)):
                s0 = DSx.displacement_score(daily, k)
                if s0["score"] >= 50 and daily[k]["c"] > daily[k]["o"]:
                    sc = s0
                    break
            if sc is None:
                continue
            ready += 1
            # 回测: entry=决策点次日起 zone=近5bar低点带, SL=低带-1.5ATR, 15bar时间退出
            lo = min(x["l"] for x in daily[max(0, i - 5):i + 1])
            zone = {"zone_low": lo, "zone_high": lo * 1.03, "invalid_price": lo * 0.97,
                    "optimal_entry": lo * 1.015}
            fill = fill_in_zone(daily, i, zone, max_bars=5, fill_mode="STRICT_LIMIT")
            if fill is None or fill.get("fill_price") is None:
                continue
            fi, fpx = fill["fill_idx"], fill["fill_price"]
            slp = zone["invalid_price"] - 1.5 * (ST.atr_of(daily, fi - 1) or 0.02 * fpx)
            ret = None
            for k in range(fi + 1, min(n, fi + 16)):
                b = daily[k]
                if b["l"] <= slp:
                    ret = (slp / fpx - 1) * 100 - FEE
                    break
                if k == min(n - 1, fi + 15):
                    ret = (b["c"] / fpx - 1) * 100 - FEE
            if ret is not None:
                pnl.append((daily[i]["t"], ret))
    LQx.PIVOT_R = _orig_pivot
    oos = [p for d, p in pnl if d >= OOS]
    if not oos:
        return {"ready": ready, "n": 0}
    w = sum(x for x in oos if x > 0); l_ = abs(sum(x for x in oos if x <= 0))
    return {"ready": ready, "n": len(oos), "avg": round(sum(oos) / len(oos), 3),
            "pf": round(w / l_, 2) if l_ > 0 else 99.0}

surface = {}
t0 = time.time()
for pv in PIVOTS:
    for tm in TOLS:
        c = run_cell(pv, tm)
        surface[f"pivot{pv}_tol{tm}"] = c
        print(f"  pivot={pv} tol={tm}: ready={c['ready']:4d} n={c['n']:4d} avg={c.get('avg')} pf={c.get('pf')}  [{time.time()-t0:.0f}s]")

# 判定: 最优格 vs 邻格; 尖峰=最优格 avg 比所有相邻格高 >2pp
best_key = max((k for k in surface if surface[k].get("n", 0) >= 30), key=lambda k: surface[k].get("avg", -99), default=None)
def neighbors(k):
    pv = int(k.split("_")[0].replace("pivot", ""))
    tm = float(k.split("_")[1].replace("tol", ""))
    out = []
    for dp in (-1, 1):
        if (pv + dp) in PIVOTS:
            out.append(f"pivot{pv+dp}_tol{tm}")
    for dt_ in (-0.2, 0.2):
        if round(tm + dt_, 1) in [round(x, 1) for x in TOLS]:
            out.append(f"pivot{pv}_tol{round(tm+dt_,1)}")
    return out

spike = None
if best_key:
    b_avg = surface[best_key].get("avg")
    nb = [surface[k].get("avg") for k in neighbors(best_key) if k in surface and surface[k].get("n", 0) >= 30]
    nb_valid = [x for x in nb if x is not None]
    spike = (len(nb_valid) > 0 and b_avg is not None and all(b_avg - x > 2.0 for x in nb_valid))
print(f"\n最优格: {best_key} → 尖峰(过拟合)警报: {spike}")
json.dump({"surface": surface, "best": best_key, "spike_alert": spike, "runtime_s": round(time.time() - t0)},
          open(r"E:\test\smc_project\research\handover\E5_参数曲面.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("已写 handover/E5_参数曲面.json")
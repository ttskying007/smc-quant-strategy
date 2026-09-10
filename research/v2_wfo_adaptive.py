# -*- coding: utf-8 -*-
"""V2 ITERATION 11: WFO Adaptive —— TradeScore 权重滚动定稿
单次扫描 READY 池存全部(分量分数+收益), 内存滚动窗:
  训练窗: 从 3 个候选权重 {equal, struct_heavy, disp_heavy} 选 top-quartile-vs-bottom 分桶差值最大的
  测试窗: 用所选权重测该窗 OOS top-三分位 vs bottom-三分位 avg
对比: WF-adaptive(每窗动态选) vs 固定 equal-weights 的池化 OOS top桶 avg。
预注册: WF-adaptive 池化 top桶 avg > 固定equal 且 多数窗(>=5/8) 占优 → 权重可WF定稿; 否则诚实保留equal。
"""
import glob, io, json, os, random, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.liquidity as LQ
import core.displacement as DS
import core.mss as MSS
import core.fvg_ob as FO
import core.entry as EN

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.20
DISP_MIN, POOL_MIN = 30, 20
files = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::5][:800]

CAND_WEIGHTS = {
    "equal": {"structure": 0.35, "sequence": 0.20, "displacement": 0.30, "location": 0.15},
    "struct_heavy": {"structure": 0.5, "sequence": 0.10, "displacement": 0.25, "location": 0.15},
    "disp_heavy": {"structure": 0.20, "sequence": 0.10, "displacement": 0.50, "location": 0.20},
}

def compo(shift, pools, dts, sc_disp, zone):
    """返回 4 分量(0-100)。"""
    s = float(shift.get("strength") or 50)
    pool_s = max(p["score"] for p in pools) if pools else 0
    structure = min(100.0, s * 0.6 + pool_s * 0.4)
    seq = min(100.0, max(0.0, 100.0 * (1 - (sum(dts)/len(dts) if dts else 30) / 30.0)))
    disp = float(sc_disp.get("score") or 0)
    loc = float(zone.get("entry_score") or 0)
    return {"structure": structure, "sequence": seq, "displacement": disp, "location": loc}

def score_of(parts, w):
    return sum(w[k] * parts[k] for k in w)

def sim_b3(daily, q, zone, wide=1.5, hold=15):
    f = EN.fill_in_zone(daily, q, zone, max_bars=6)
    if f is None or f["fill_price"] is None:
        return None
    k0, px = f["fill_idx"], f["fill_price"]
    if k0 + hold + 1 >= len(daily):
        return None
    try:
        from core.structure import atr_of
        a_ = atr_of(daily, k0) or px * 0.025
    except Exception:
        a_ = px * 0.025
    sl = zone["invalid_price"] - wide * a_
    for k in range(k0 + 1, min(len(daily), k0 + hold + 1)):
        if daily[k]["l"] <= sl:
            return ((sl / px - 1) * 100) - FEE
    return ((daily[min(len(daily) - 1, k0 + hold)]["c"] / px - 1) * 100) - FEE

def _dnum(d8):
    import datetime as dt
    return dt.date(int(d8[:4]), int(d8[4:6]), int(d8[6:8]))

recs = []  # (d8, parts, net)
for fp in files:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    if len(raw) < 150:
        continue
    daily = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
              "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    n = len(daily)
    for i in range(150, n):
        if daily[i]["t"] < "20230701":
            continue
        pools = LQ.liquidity_pools(daily, i)
        ssl = [p for p in pools if p["side"] == "SSL" and p["score"] >= POOL_MIN]
        if not ssl:
            continue
        b = daily[i]
        try:
            from core.structure import atr_of
            a_ = atr_of(daily, i - 1) or 0
        except Exception:
            a_ = 0
        atr_pct = (a_ / (daily[i-1]["c"] or 1)) if a_ else 0.02
        tol = max(0.003, atr_pct * 0.5)
        pool = ssl[0]["price"]
        if b["l"] <= pool * (1 - tol) and b["c"] > pool:
            ph = max(x["h"] for x in daily[max(0, i-5):i]) if i >= 5 else b["h"]
            for k in range(i + 1, min(n, i + 6)):
                if daily[k]["c"] > ph:
                    sc_disp = DS.displacement_score(daily, k)
                    if sc_disp["score"] >= DISP_MIN:
                        for m in range(k, min(n, k + 13)):
                            s5 = MSS.structure_shift(daily, m)
                            if s5 and s5["direction"] == "LONG":
                                f6 = FO.fvg_at(daily, m)
                                ob6 = FO.order_block(daily, m, "BULL")
                                if f6 or ob6:
                                    poi = f6 if f6 else ob6
                                    for q in range(m + 1, min(n, m + 11)):
                                        if poi["low"] <= daily[q]["l"] <= poi["high"] * 1.02:
                                            zone = EN.entry_zone(poi, price=daily[q]["c"],
                                                                  invalid_price=poi["low"] * 0.97, atr_pct=atr_pct)
                                            if zone is None:
                                                break
                                            try:
                                                dts = [(_dnum(daily[k]["t"]) - _dnum(daily[i]["t"])).days,
                                                       (_dnum(daily[m]["t"]) - _dnum(daily[k]["t"])).days,
                                                       (_dnum(daily[q]["t"]) - _dnum(daily[m]["t"])).days]
                                            except Exception:
                                                dts = []
                                            p = sim_b3(daily, q, zone)
                                            if p is not None:
                                                recs.append((daily[q]["t"], compo(s5, pools, dts, sc_disp, zone), p))
                                            break
                                        if daily[q]["c"] < poi["low"] * 0.97:
                                            break
                                break
                        break
                elif daily[k]["c"] < pool * (1 - 2 * tol):
                    break

print(f"READY 池: {len(recs)} 笔", flush=True)

def top_bottom_gap(sel, w):
    """sel: (d8, parts, net) 列表。按 score 排序, top 三分位 vs bottom 三分位 avg 差。"""
    if len(sel) < 6:
        return None, None
    scored = sorted(((score_of(r[1], w), r[2]) for r in sel), key=lambda x: x[0])
    n = len(scored)
    t = n // 3
    top = scored[n - t:]
    bot = scored[:t]
    t_avg = sum(x[1] for x in top) / len(top)
    b_avg = sum(x[1] for x in bot) / len(bot)
    return t_avg - b_avg, t_avg

def shift_ym(m, n):
    y, mm = int(m[:4]), int(m[4:6])
    t_ = y * 12 + mm - 1 + n
    return f"{t_//12:04d}{t_%12+1:02d}"

by_month = defaultdict(list)
for r in recs:
    by_month[r[0][:6]].append(r)
months = sorted(by_month)

# 预选候选(每窗 train 选 top-bottom gap 最大者)
windows = []
cur_m = months[0]
while True:
    tr_end = shift_ym(cur_m, 12)
    te_start, te_end = tr_end, shift_ym(tr_end, 3)
    if te_start > months[-1]:
        break
    tr_tr = [r for m in months if cur_m <= m < tr_end for r in by_month[m]]
    te_tr = [r for m in months if te_start <= m < te_end for r in by_month[m]]
    if len(tr_tr) >= 30 and len(te_tr) >= 8:
        best_k, best_gap = None, -9e9
        for k, w in CAND_WEIGHTS.items():
            gap, _ = top_bottom_gap(tr_tr, w)
            if gap is not None and gap > best_gap:
                best_gap, best_k = gap, k
        # 测试窗: 该窗内 top/bottom avg(用所选k与equal各算一次, 供池化比较)
        tg_wf, tavg_wf = top_bottom_gap(te_tr, CAND_WEIGHTS[best_k])
        tg_eq, tavg_eq = top_bottom_gap(te_tr, CAND_WEIGHTS["equal"])
        windows.append({"test": f"{te_start}~{te_end}", "n": len(te_tr), "sel": best_k,
                        "wf_top_avg": round(tavg_wf, 3) if tavg_wf is not None else None,
                        "eq_top_avg": round(tavg_eq, 3) if tavg_eq is not None else None,
                        "wf_beats_eq": (tavg_wf or -9) > (tavg_eq or -9)})
    cur_m = shift_ym(cur_m, 3)

# 池化 OOS 对比: 用各窗 WF 所选权重的 top 桶合并 vs equal 的 top 桶合并
oos_all = [r for r in recs if r[0] >= OOS]
sel_top, eq_top = [], []
for w_ in windows:
    pass
# 简化池化: 全局 OOS 上 equal vs 各候选的 top 桶 avg
global_res = {}
for k, w in CAND_WEIGHTS.items():
    gap, tavg = top_bottom_gap(oos_all, w)
    global_res[k] = {"top_avg": round(tavg, 3) if tavg is not None else None, "gap": round(gap, 3) if gap is not None else None}
    print(f"  全局OOS {k}: top_avg={global_res[k]['top_avg']} top-bottom_gap={global_res[k]['gap']}", flush=True)

wf_wins = sum(1 for w_ in windows if w_["wf_beats_eq"])
print(f"\nWF 逐窗: {[(w_['test'], w_['sel'], w_['wf_beats_eq']) for w_ in windows]}")
print(f"WF 选择战胜 equal 窗数: {wf_wins}/{len(windows)}")

verdict = {"wf_wins_windows": f"{wf_wins}/{len(windows)}",
           "global_best_cand": max(global_res, key=lambda k: (global_res[k]['top_avg'] or -9)),
           "equal_top_avg": global_res["equal"]["top_avg"],
           "struct_heavy_top_avg": global_res["struct_heavy"]["top_avg"],
           "disp_heavy_top_avg": global_res["disp_heavy"]["top_avg"]}
out = {"n_pool": len(recs), "windows": windows, "global_oos": global_res, "verdict": verdict}
# 判定: WF adaptive(逐窗选) 池化 top 是否优于固定 equal —— 用所有窗 WF 所选 top 平均
wf_top_avgs = [w_["wf_top_avg"] for w_ in windows if w_["wf_top_avg"] is not None]
eq_top_avgs = [w_["eq_top_avg"] for w_ in windows if w_["eq_top_avg"] is not None]
verdict["wf_pooled_top_avg"] = round(sum(wf_top_avgs)/len(wf_top_avgs), 3) if wf_top_avgs else None
verdict["eq_pooled_top_avg"] = round(sum(eq_top_avgs)/len(eq_top_avgs), 3) if eq_top_avgs else None
verdict["wf_adaptive_beats_equal"] = (verdict["wf_pooled_top_avg"] or -9) > (verdict["eq_pooled_top_avg"] or -9)
print(f"\n池化 top avg: WF-adaptive={verdict['wf_pooled_top_avg']} vs equal={verdict['eq_pooled_top_avg']}")
print(f"→ WF adaptive 优于固定equal: {verdict['wf_adaptive_beats_equal']} | 权重定稿依据: WF胜窗 {wf_wins}/{len(windows)}")

json.dump(out, open(r"E:\test\smc_project\research\handover\V2迭代11_WFO权重.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("已写 handover/V2迭代11_WFO权重.json")
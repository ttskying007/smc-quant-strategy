# -*- coding: utf-8 -*-
"""v4_family_x_escore.py —— V3-D: 结构腿 Family × E-score 交叉(预注册)
背景: D1 E-score 已证【事件腿】单调(ρ=0.928)。但【结构腿】(A_full 等 Family)与 E
的关系从未验证 —— 若结构腿在低 E 也退化, 则 E 仓位系数可统一用于两腿; 若结构腿
对 E 不敏感(E 中性), 则两腿天然互补(事件腿 E 调仓 + 结构腿全天候) → 组合分散价值。

设计: 重放 A_full 族(与 Family DB 同定义/universe/退出), 每笔标注决策时点 E(从
escore_history 快照读, 60 日回填已就绪; 历史更长窗口用 core.escore 现算 F1 快照
慢扫——限 OOS 20250701+ 与快照重叠期 20260612+)。
分组: E 分三档(Q1/Q2 低, Q3 中, Q4/Q5 高——按快照分布切)。
预注册判定:
  S1 单调性: 高E组avg > 中E组 > 低E组(严格序) → 结构腿 E 敏感
  S2 spread: 高低差 ≥ 1.0pp → E 系数两腿统一; < 1.0pp → E 中性(两腿互补论据)
  S3 样本: 每组 n ≥ 30 否则该组 UNKNOWN
输出: handover/V4_结构腿E交叉.json"""
import glob, io, json, os, random, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.liquidity as LQ
import core.displacement as DSP
import core.mss as MSS
import core.fvg_ob as FO
from core.setup_exit import settle_setup
from core.structure import atr_of

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
FEE = 0.2
# E 快照: 优先全历史回填版(780日), 回退 60 日滚动版
E_HIST = {}
for _p in (r"E:\test\smc_project\research\handover\escore_history_full.json",
           r"E:\test\smc_project\research\handover\escore_history.json"):
    try:
        _h = json.load(open(_p, encoding="utf-8"))
        _d = {d["d8"]: d.get("e") for d in _h.get("days", []) if d.get("e") is not None}
        if len(_d) > len(E_HIST):
            E_HIST = _d
    except Exception:
        pass
e_days = sorted(E_HIST)
D_FROM, D_TO = (e_days[0], e_days[-1]) if e_days else (None, None)
print(f"E 快照窗口: {D_FROM}~{D_TO} ({len(E_HIST)} 日)")

FILES = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::2]   # 全历史→恢复1/2抽样与FamilyDB一致

def a_full_at(daily, i):
    """A_full 判定(与 Family DB 同语义)。"""
    n = len(daily)
    if i < 60:
        return None
    atr = atr_of(daily, i - 1) or 0
    atr_pct = atr / (daily[i - 1]["c"] or 1) if atr else 0.02
    tol = max(0.003, atr_pct * 0.5)
    w0 = max(60, i - 40)
    pools = LQ.liquidity_pools(daily, w0 + 1)
    ssl = [p for p in pools if p["side"] == "SSL" and p["score"] >= 40]
    if not ssl:
        return None
    pool = ssl[0]
    sw_i = None
    for k in range(w0 + 2, i + 1):
        b = daily[k]
        if b["l"] <= pool["price"] * (1 - tol) and b["c"] > pool["price"]:
            sw_i = k
            break
        if b["c"] < pool["price"] * (1 - 2 * tol):
            break
    if sw_i is None:
        return None
    ph = max(x["h"] for x in daily[max(0, sw_i - 5):sw_i])
    rc_i = None
    for k in range(sw_i + 1, min(n, sw_i + 6)):
        if daily[k]["c"] > ph:
            rc_i = k
            break
        if daily[k]["c"] < pool["price"] * (1 - 2 * tol):
            break
    if rc_i is None:
        return None
    dp_i = None
    for k in range(rc_i, min(n, rc_i + 6)):
        sc = DSP.displacement_score(daily, k)
        if sc["score"] >= 50 and daily[k]["c"] > daily[k]["o"]:
            dp_i = k
            break
    if dp_i is None:
        return None
    sh2 = None
    for k in range(dp_i, min(n, dp_i + 13)):
        s5 = MSS.structure_shift(daily, k)
        if s5 and s5["direction"] == "LONG":
            sh2 = k
            break
    if sh2 is None:
        return None
    for k in range(sh2, min(n, sh2 + 4)):
        f = FO.fvg_at(daily, k)
        poi = f if f else FO.order_block(daily, k, "BULL")
        if poi:
            for q in range(k + 1, min(n, k + 9)):
                b = daily[q]
                if b["c"] < poi["low"] * 0.97:
                    return None
                if poi["low"] <= b["l"] <= poi["high"] * 1.02:
                    return {"poi": poi}
            return None
    return None

# E 三档切分(按快照分布 33%/67%)
evals = sorted(E_HIST.values())
if evals:
    q33, q67 = evals[len(evals) // 3], evals[len(evals) * 2 // 3]
else:
    q33 = q67 = None
def e_band(e):
    if e is None or q33 is None:
        return None
    if e <= q33:
        return "low(Q1/Q2)"
    if e <= q67:
        return "mid(Q3)"
    return "high(Q4/Q5)"

groups = {"low(Q1/Q2)": [], "mid(Q3)": [], "high(Q4/Q5)": []}
t0 = time.time()
n_scan = 0
for fp in FILES:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    if len(raw) < 200:
        continue
    daily = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
              "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    n = len(daily)
    for i in range(150, n - 25):
        d8 = daily[i]["t"]
        if not (D_FROM <= d8 <= D_TO) or d8 < "20250701":   # OOS only(判定期)
            continue
        n_scan += 1
        band = e_band(E_HIST.get(d8))
        if band is None:
            continue
        s = a_full_at(daily, i)
        if s is None:
            continue
        res = settle_setup(daily, i, s, fee_pct=FEE)
        if res and res["status"] in ("SL", "TP", "TIME"):
            groups[band].append((d8, res["ret_pct"]))
print(f"扫描决策点 {n_scan} (E窗内), 用时 {time.time()-t0:.0f}s")

def stats(v):
    if not v:
        return {"n": 0}
    vals = [p for _, p in v]
    w = sum(x for x in vals if x > 0)
    l_ = abs(sum(x for x in vals if x <= 0))
    return {"n": len(vals), "avg": round(sum(vals) / len(vals), 3),
            "wr": round(len([x for x in vals if x > 0]) / len(vals) * 100, 1),
            "pf": round(w / l_, 2) if l_ > 0 else None}

G = {k: stats(v) for k, v in groups.items()}
spread = None
if all(G[k].get("avg") is not None for k in G):
    spread = round(G["high(Q4/Q5)"]["avg"] - G["low(Q1/Q2)"]["avg"], 3)
monotonic = (G["high(Q4/Q5)"].get("avg") is not None
             and G["high(Q4/Q5)"]["avg"] > G["mid(Q3)"].get("avg", -99) > G["low(Q1/Q2)"].get("avg", -99))
n_ok = all(G[k]["n"] >= 30 for k in G)

out = {"window": f"E快照期 {D_FROM}~{D_TO}", "e_cut": {"q33": q33, "q67": q67},
       "groups": G, "spread_high_minus_low_pp": spread,
       "preregistered": {
           "S1_严格单调(高>中>低)": monotonic,
           "S2_spread≥1.0(两腿统一)": spread is not None and spread >= 1.0,
           "S2_E中性(<1.0, 两腿互补)": spread is not None and spread < 1.0,
           "S3_各组n≥30": n_ok},
       "conclusion_if_valid": ("E系数可统一用于两腿" if spread is not None and spread >= 1.0
                                else "结构腿E中性→与事件腿天然互补(组合分散价值)")}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_结构腿E交叉.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
for k in G:
    print(f"  {k:12s}: {G[k]}")
print(f"spread = {spread}pp, 单调={monotonic}, n_ok={n_ok}")
print("已写 handover/V4_结构腿E交叉.json")
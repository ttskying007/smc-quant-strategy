# -*- coding: utf-8 -*-
"""v4_e_rev2_family.py —— E_rev2(晚扫劣)机理: 家族层 vs POI 层分解(预注册 #32)
背景: E_rev2 n=67540 avg+0.68 < A_full +1.41 → Δ−0.73pp "晚扫劣"(已锁判定)。
未解: 晚扫的劣势来自哪层?
  H1 POI 层: 晚扫→链的后半段 POI 离 sweep 更远(位移衰竭) → POI 质量差
  H2 距离层: 晚扫→回踩更深才到 POI(fill 价更差但深折价假设已被否 avg 仅 0.066%)
  H3 队列层: 晚扫→结构性趋弱的时间点聚集在弱市(E 相关)
可分变量: 决策点 i 与 sweep 的距离(k−sw_i), POI 与 sweep 距离, 决策点 E。
预注册:
  F1 按决策滞后(late=决策点距sweep>3bar)分桶, A_full(对照) vs E_rev2: late 劣势
     主要出现在 [POI质量差] 还是 [时间聚集]?  —— 用"同滞后窗内 E_rev2 vs A_full 的Δ"
  F2 若晚扫劣势在 E 低档更大(交互) → 队列层补充
  F3 若各 E 档内晚扫仍劣 → 纯信号层(POI 衰竭), 如实报
方法: 复用 Family DB 同判定, 按 E 分档 × [A_full, E_rev2] 双臂内对比(避开全量重扫,
只重放 20250701+ OOS 且两臂都有判定的决策点)。"""
import glob, io, json, os, sys, time
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import core.liquidity as LQ
import core.displacement as DSP
import core.mss as MSS
import core.fvg_ob as FO
from core.structure import atr_of
from core.setup_exit import settle_setup

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
FEE = 0.2
E_HIST = {d["d8"]: d.get("e") for d in json.load(open(
    r"E:\test\smc_project\research\handover\escore_history_full.json", encoding="utf-8")
).get("days", []) if d.get("e") is not None}
# 全历史分档(与交叉实验锁定基准一致)
Q33, Q67 = 0.4559, 0.5562
def band(e):
    return None if e is None else ("low" if e <= Q33 else "mid" if e <= Q67 else "high")

FILES = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::2][:2000]

def arms_at(daily, i):
    """在决策点 i 同时评估两臂(同次链扫描):
    A_full: shift→POI→sweep-into(决策点 i 是 sweep 的当下)
    E_rev2: 与 A_full 同 POI, 但决策点是晚扫(i 在 sweep 之后, 回踩)
    返回 (ret_A or None, ret_rev2 or None, 滞后bar数)"""
    n = len(daily)
    if i < 60:
        return None, None, None
    atr = atr_of(daily, i - 1) or 0
    atr_pct = atr / (daily[i - 1]["c"] or 1) if atr else 0.02
    tol = max(0.003, atr_pct * 0.5)
    w0 = max(60, i - 40)
    pools = LQ.liquidity_pools(daily, w0 + 1)
    ssl = [p for p in pools if p["side"] == "SSL" and p["score"] >= 40]
    if not ssl:
        return None, None, None
    pool = ssl[0]
    sw_i = None
    for k in range(w0 + 2, i + 1):
        b = daily[k]
        if b["l"] <= pool["price"] * (1 - tol) and b["c"] > pool["price"]:
            sw_i = k
            break
        if b["c"] < pool["price"] * (1 - 2 * tol):
            return None, None, None
    if sw_i is None:
        return None, None, None
    lag = i - sw_i
    ph = max(x["h"] for x in daily[max(0, sw_i - 5):sw_i])
    rc_i = None
    for k in range(sw_i + 1, min(n, sw_i + 6)):
        if daily[k]["c"] > ph:
            rc_i = k
            break
        if daily[k]["c"] < pool["price"] * (1 - 2 * tol):
            return None, None, None
    if rc_i is None:
        return None, None, None
    dp_i = None
    for k in range(rc_i, min(n, rc_i + 6)):
        sc = DSP.displacement_score(daily, k)
        if sc["score"] >= 50 and daily[k]["c"] > daily[k]["o"]:
            dp_i = k
            break
    if dp_i is None:
        return None, None, None
    sh2 = None
    for k in range(dp_i, min(n, dp_i + 13)):
        s5 = MSS.structure_shift(daily, k)
        if s5 and s5["direction"] == "LONG":
            sh2 = k
            break
    if sh2 is None:
        return None, None, None
    poi = None
    for k in range(sh2, min(n, sh2 + 4)):
        f = FO.fvg_at(daily, k)
        p = f if f else FO.order_block(daily, k, "BULL")
        if p:
            poi = p
            break
    if poi is None:
        return None, None, None
    # A_full: 决策点=i(要求 i 就是 sweep 日; lag=0 的情形)
    retA = None
    if lag == 0:
        r = settle_setup(daily, i, {"poi": poi}, fee_pct=FEE)
        if r and r["status"] in ("SL", "TP", "TIME"):
            retA = r["ret_pct"]
    # E_rev2: 同 POI 在 i 的回踩判定(晚扫语义: i 已过 sweep, 价格回踩进 POI)
    retR = None
    if lag > 0:
        b = daily[i]
        if poi["low"] <= b["l"] <= poi["high"] * 1.02 and b["c"] > poi["low"]:
            r = settle_setup(daily, i, {"poi": poi}, fee_pct=FEE)
            if r and r["status"] in ("SL", "TP", "TIME"):
                retR = r["ret_pct"]
    return retA, retR, lag

stats = defaultdict(list)     # (arm, band) → rets
t0 = time.time()
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
        if d8 < "20250701":
            continue
        bd = band(E_HIST.get(d8))
        retA, retR, lag = arms_at(daily, i)
        if retA is not None:
            stats[("A", bd)].append(retA)
        if retR is not None:
            stats[("R2", bd)].append(retR)
print(f"{time.time()-t0:.0f}s")
out = {}
for arm in ("A", "R2"):
    for b_ in ("low", "mid", "high", None):
        v = stats.get((arm, b_), [])
        if v:
            out[f"{arm}_{b_}"] = {"n": len(v), "avg": round(sum(v)/len(v), 3)}
# 判定: 各 E 档内 R2 vs A 的 Δ
verdict = {}
for b_ in ("low", "mid", "high"):
    a = out.get(f"A_{b_}", {}).get("avg")
    r = out.get(f"R2_{b_}", {}).get("avg")
    if a is not None and r is not None:
        verdict[f"ΔR2−A @{b_}"] = round(r - a, 3)
out["_preregistered"] = {
    "F3_各档内晚扫仍劣(纯信号层)": bool(all(
        verdict.get(f"ΔR2−A @{b_}", 0) < 0 for b_ in ("low", "mid", "high")
        if f"ΔR2−A @{b_}" in verdict)),
    "deltas": verdict,
    "note": "各 E 档内同 POI 双臂对照 → 排除队列层(E 相关的时间聚集), 剩余=POI 衰竭层",
}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_晚扫机理分解.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=1))
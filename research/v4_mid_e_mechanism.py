# -*- coding: utf-8 -*-
"""v4_mid_e_mechanism.py —— 结构腿 mid-E 峰值机理检验(预注册)
背景(V4_结构腿E交叉): OOS A_full avg: low −0.02 / mid +4.66 / high +3.35 —— 非单调。
假设 H1(跳过机理): E 越高 → POI 回踩成交率越低(过热环境价格直接跑过 POI) +
     失效越快(INVALIDATED), 高 E 的已成交子集是"碰巧没跑掉"的较弱样本。
假设 H2(成交质量): 已成交子集中 mid-E 仍最优(已证)。
检验: 重放 A_full 判定(与 Family DB 同语义), 按决策时点 E 档统计:
  attempted(链完成=尝试挂单) / filled(5bar 内 STRICT_LIMIT 成交) / invalidated(前失效)
  → fill_rate 与 invalid_rate 随 E 的梯度。
预注册:
  M1 fill_rate(high) < fill_rate(mid) − 5pp → 跳过机理成立
  M2 invalid_rate 随 E 上升 → 失效机理成立
  M3 双否 → mid 峰值另有原因(如下一步: 成交时点市场微观结构), 如实报
输出: handover/V4_midE机理.json"""
import glob, io, json, os, sys, time
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.liquidity as LQ
import core.displacement as DSP
import core.mss as MSS
import core.fvg_ob as FO
from core.entry import fill_in_zone
from core.structure import atr_of

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
FEE = 0.2
E_HIST = {}
try:
    _h = json.load(open(r"E:\test\smc_project\research\handover\escore_history_full.json",
                       encoding="utf-8"))
    E_HIST = {d["d8"]: d.get("e") for d in _h.get("days", []) if d.get("e") is not None
              and d["d8"] >= "20250701"}        # OOS 判定期
except Exception:
    pass
_es = sorted(E_HIST.values())
Q33, Q67 = _es[len(_es) // 3], _es[len(_es) * 2 // 3]
def band(e):
    return None if e is None else ("low" if e <= Q33 else "mid" if e <= Q67 else "high")

FILES = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::2][:2000]

def a_full_poi(daily, i):
    """A_full 判定(Family DB 同语义) → poi or None。"""
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
            return poi
    return None

stats = defaultdict(lambda: {"attempt": 0, "filled": 0, "invalid": 0, "rets": []})
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
        bd = band(E_HIST.get(d8))
        if bd is None:
            continue
        poi = a_full_poi(daily, i)
        if poi is None:
            continue
        zone = {"zone_low": poi["low"], "zone_high": poi["high"],
                "invalid_price": poi["low"] * 0.97, "optimal_entry": poi["mid"]}
        stats[bd]["attempt"] += 1
        fill = fill_in_zone(daily, i, zone, max_bars=5, fill_mode="STRICT_LIMIT")
        if fill and fill.get("fill_price"):
            stats[bd]["filled"] += 1
            # 简版收益(15bar TIME 口径与交叉实验一致)
            fi, fpx = fill["fill_idx"], fill["fill_price"]
            lo_idx = min(n - 1, fi + 15)
            # SL 近似: invalid − 1.5×ATR(决策点)
            atr = atr_of(daily, i) or fpx * 0.025
            slp = zone["invalid_price"] - 1.5 * atr
            ret = None
            for k in range(fi + 1, lo_idx + 1):
                if daily[k]["l"] <= slp:
                    ret = (slp / fpx - 1) * 100 - FEE
                    break
            if ret is None:
                ret = (daily[lo_idx]["c"] / fpx - 1) * 100 - FEE
            stats[bd]["rets"].append(ret)
        elif fill and fill.get("mode") == "INVALIDATED_BEFORE_FILL":
            stats[bd]["invalid"] += 1

print(f"扫描 {time.time()-t0:.0f}s")
out = {}
for bd in ("low", "mid", "high"):
    s = stats[bd]
    att = s["attempt"]
    fill_rate = round(s["filled"] / att * 100, 1) if att else None
    inv_rate = round(s["invalid"] / att * 100, 1) if att else None
    avg = round(sum(s["rets"]) / len(s["rets"]), 3) if s["rets"] else None
    out[bd] = {"attempt": att, "filled": s["filled"], "invalidated": s["invalid"],
               "fill_rate_pct": fill_rate, "invalid_rate_pct": inv_rate,
               "avg_ret_filled": avg, "n_ret": len(s["rets"])}

fr = {b: out[b]["fill_rate_pct"] for b in out}
ir = {b: out[b]["invalid_rate_pct"] for b in out}
verdict = {
    "M1_跳过机理(fill high < mid−5pp)": bool(
        fr.get("high") is not None and fr.get("mid") is not None
        and fr["high"] < fr["mid"] - 5),
    "M2_失效机理(invalid 随 E 升)": bool(
        ir.get("low") is not None and ir.get("mid") is not None and ir.get("high") is not None
        and ir["low"] < ir["mid"] < ir["high"]),
    "M3_双否→mid峰另有原因": None,
}
verdict["M3_双否→mid峰另有原因"] = not (verdict["M1_跳过机理(fill high < mid−5pp)"]
                                        or verdict["M2_失效机理(invalid 随 E 升)"])
out["_preregistered"] = verdict
out["_e_cut"] = {"q33": Q33, "q67": Q67}
out["_note"] = "OOS 20250701+; attempted=A_full 链完成(挂单尝试); fill=5bar STRICT_LIMIT; 与 V4_结构腿E交叉 同 universe"
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_midE机理.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
for bd in ("low", "mid", "high"):
    print(f"  {bd:4s}: {out[bd]}")
print("预注册:", json.dumps(verdict, ensure_ascii=False))
print("已写 handover/V4_midE机理.json")
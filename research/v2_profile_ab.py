# -*- coding: utf-8 -*-
"""Profile 参数族 A/B: 固定参数 vs 聚类参数族(新引擎 READY 链)
蓝图 §78 Adaptive 增量实验第一级: Fixed vs Profile-Adaptive。
方法: READY 链(800股)同一入场, 退出/参数按 profile_family_params:
  A臂 = 固定参数(max_hold=15, sl_buf=1.5, disp_min=50 —— 即 B3 基线)
  B臂 = Profile 参数族: max_hold/sl_buf 按 profile_cluster(stock@i) 调整
预注册: B 臂 OOS avg 与 PF 双升才晋级研究(距生产还需 WF)。"""
import glob, io, json, os, random, sys
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.liquidity as LQ
import core.displacement as DS
import core.mss as MSS
import core.fvg_ob as FO
import core.entry as EN
import core.profile as PR

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.20
files = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::5][:800]

def sim_adaptive(daily, q, zone, wide, max_hold):
    """宽SL+时间出场(参数化版 B3)。"""
    f = EN.fill_in_zone(daily, q, zone, max_bars=6)
    if f is None or f["fill_price"] is None:
        return None
    k0, px = f["fill_idx"], f["fill_price"]
    if k0 + max_hold + 1 >= len(daily):
        return None
    try:
        from core.structure import atr_of
        a_ = atr_of(daily, k0) or px * 0.025
    except Exception:
        a_ = px * 0.025
    sl = zone["invalid_price"] - wide * a_
    for k in range(k0 + 1, min(len(daily), k0 + max_hold + 1)):
        if daily[k]["l"] <= sl:
            return ((sl / px - 1) * 100) - FEE
    return ((daily[min(len(daily) - 1, k0 + max_hold)]["c"] / px - 1) * 100) - FEE

armA, armB = [], []
profiles_seen = {}
for fp in files:
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
        if daily[i]["t"] < "20230701":
            continue
        pools = LQ.liquidity_pools(daily, i)
        ssl = [p for p in pools if p["side"] == "SSL" and p["score"] >= 40]
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
                                            # A臂: 固定参数(B3基线)
                                            pA = sim_adaptive(daily, q, z, wide=1.5, max_hold=15)
                                            # B臂: profile 参数族
                                            prof = PR.stock_profile(daily, q, window=120)
                                            cluster = PR.profile_cluster(prof)
                                            fparams = PR.profile_family_params(cluster)
                                            pB = sim_adaptive(daily, q, z,
                                                             wide=fparams["sl_buf_atr"] * 3,  # 族值0.4-0.75 → 宽度1.2-2.25
                                                             max_hold=fparams["max_hold"])
                                            d8 = daily[q]["t"]
                                            if pA is not None:
                                                armA.append((code, d8, pA))
                                            if pB is not None:
                                                armB.append((code, d8, pB))
                                            profiles_seen[cluster or "none"] = profiles_seen.get(cluster or "none", 0) + 1
                                            break
                                        if daily[q]["c"] < poi["low"] * 0.97:
                                            break
                                break
                        break
                elif daily[k]["c"] < pool * (1 - 2 * tol):
                    break

random.seed(42)
def stats(arm, oos):
    sel = [p for c, d, p in arm if (d >= OOS) == oos]
    if not sel:
        return {"n": 0}
    w = [x for x in sel if x > 0]
    l_ = [x for x in sel if x <= 0]
    return {"n": len(sel), "avg": round(sum(sel)/len(sel), 3), "wr": round(len(w)/len(sel), 3),
            "pf": round(sum(w)/abs(sum(l_)), 2) if l_ else 99}

def boot(arm, oos, iters=2000):
    sel = [p for c, d, p in arm if (d >= OOS) == oos]
    if len(sel) < 15:
        return None
    ms = []
    for _ in range(iters):
        s = random.choices(sel, k=len(sel))
        ms.append(sum(s)/len(s))
    ms.sort()
    return [round(ms[int(0.025*len(ms))], 3), round(ms[int(0.975*len(ms))], 3)]

out = {"nA": len(armA), "nB": len(armB), "profile_dist": profiles_seen,
       "A_fixed": {"IS": stats(armA, False), "OOS": stats(armA, True), "OOS_ci": boot(armA, True)},
       "B_profile": {"IS": stats(armB, False), "OOS": stats(armB, True), "OOS_ci": boot(armB, True)}}
print(f"A: {len(armA)} | B: {len(armB)} | profile分布: {profiles_seen}")
for k in ("A_fixed", "B_profile"):
    v = out[k]
    print(f"\n{k}: IS={v['IS']}")
    print(f"       OOS={v['OOS']} CI={v['OOS_ci']}")
a, b = out["A_fixed"]["OOS"], out["B_profile"]["OOS"]
verdict = {"B_sample_ok": b.get("n", 0) >= 50,
           "B_beats_A_avg": b.get("avg", -99) > a.get("avg", -99),
           "B_beats_A_pf": b.get("pf", 0) > a.get("pf", 0)}
verdict["profile_adaptive_helps"] = all(verdict.values())
out["verdict"] = verdict
print(f"\n== 预注册判定(研究晋级线: OOS avg+PF双升) ==")
print(f"  样本>=50: {verdict['B_sample_ok']} | avg {b.get('avg')}>{a.get('avg')}: {verdict['B_beats_A_avg']} | PF {b.get('pf')}>{a.get('pf')}: {verdict['B_beats_A_pf']}")
print(f"  → Profile 参数族有效: {verdict['profile_adaptive_helps']}")

json.dump(out, open(r"E:\test\smc_project\research\handover\Profile参数族AB.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("已写 handover/Profile参数族AB.json")
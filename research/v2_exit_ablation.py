# -*- coding: utf-8 -*-
"""V2 退出结构修复实验: 三臂消融(单一假设=退出结构是右尾截断主因)
A臂(对照) = B1 快TP基线(迭代7/8的B臂: SL结构+TP1半仓@池1/TP2@池2/TP3@池3, ≤15根)
B2臂      = 延迟TP+宽SL: SL放宽至 invalid−1.5×ATR; TP1 需 bar>=8 根后才有效(时间朋友);
            TP1 后 SL 移 BE; TP2 半仓; 其余 15 根收盘
B3臂      = 纯时间朋友: 同 B2 的 SL, 无 TP 池目标, 15 根收盘全出(检验池目标是否有害)
同 READY 集同成本, IS/OOS + WR/avg/PF + MFE利用效率(实收/MFE)。
"""
import glob, io, json, os, random, sys
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.liquidity as LQ
import core.displacement as DS
import core.mss as MSS
import core.fvg_ob as FO
import core.entry as EN
import core.risk as RK

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.20
files = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::5][:800]

# ---- 复用迭代7/8的 READY 收集(与 v2_entry_tpsl_ab.py 完全同口径) ----
ready = []
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
                                            ready.append((code, daily, q, poi))
                                            break
                                        if daily[q]["c"] < poi["low"] * 0.97:
                                            break
                                break
                        break
                elif daily[k]["c"] < pool * (1 - 2 * tol):
                    break
print(f"READY 链: {len(ready)}", flush=True)

def sim_b1(daily, q, zone, tps):
    """B1 快TP基线(与迭代7/8 B臂同语义)。"""
    f = EN.fill_in_zone(daily, q, zone, max_bars=6)
    if f is None or f["fill_price"] is None:
        return None, None
    k0, px = f["fill_idx"], f["fill_price"]
    if k0 + 15 >= len(daily):
        return None, None
    sl, tp1, tp2, tp3 = tps["sl"], tps["tp1"], tps["tp2"], tps["tp3"]
    rem, realised = 1.0, 0.0
    for k in range(k0 + 1, min(len(daily), k0 + 16)):
        b = daily[k]
        if b["l"] <= sl:
            realised += rem * ((sl / px - 1) * 100); rem = 0.0
            break
        if rem > 0.51 and b["h"] >= tp1:
            realised += 0.5 * ((tp1 / px - 1) * 100); rem -= 0.5
        if rem > 0.21 and b["h"] >= tp2:
            realised += 0.5 * ((tp2 / px - 1) * 100); rem -= 0.5
        if b["h"] >= tp3:
            realised += rem * ((tp3 / px - 1) * 100); rem = 0.0
            break
    if rem > 0:
        realised += rem * ((daily[min(len(daily)-1, k0 + 15)]["c"] / px - 1) * 100)
    return realised - FEE, (k0, px)

def sim_delayed(daily, q, zone, tps, wide=1.5, tp1_delay=8, be_after_tp1=True):
    """B2 延迟TP+宽SL+BE+时间朋友。
    SL = zone.invalid − wide×ATR_abs(结构失效再留宽缓冲)
    TP1 仅在 fill 后 tp1_delay 根后才有效(时间朋友); TP2@池2; 尾仓 15 根收盘。
    TP1 后 SL→BE(px)。"""
    f = EN.fill_in_zone(daily, q, zone, max_bars=6)
    if f is None or f["fill_price"] is None:
        return None, None
    k0, px = f["fill_idx"], f["fill_price"]
    if k0 + 15 >= len(daily):
        return None, None
    atr_abs = px * 0.025
    try:
        from core.structure import atr_of
        a_ = atr_of(daily, k0) or 0
        if a_:
            atr_abs = a_
    except Exception:
        pass
    sl0 = zone["invalid_price"] - wide * atr_abs
    sl = sl0
    tp1, tp2, tp3 = tps["tp1"], tps["tp2"], tps["tp3"]
    rem, realised = 1.0, 0.0
    tp1_hit = False
    for k in range(k0 + 1, min(len(daily), k0 + 16)):
        b = daily[k]
        age = k - k0
        if b["l"] <= sl:
            realised += rem * ((sl / px - 1) * 100); rem = 0.0
            break
        if not tp1_hit and age >= tp1_delay and b["h"] >= tp1:
            realised += 0.5 * ((tp1 / px - 1) * 100); rem -= 0.5
            tp1_hit = True
            if be_after_tp1:
                sl = max(sl, px)  # BE
        if rem > 0.21 and b["h"] >= tp2:
            realised += 0.5 * ((tp2 / px - 1) * 100); rem -= 0.5
        # 无 TP3 快出: 时间朋友, 尾仓持有到底
    if rem > 0:
        realised += rem * ((daily[min(len(daily)-1, k0 + 15)]["c"] / px - 1) * 100)
    return realised - FEE, (k0, px)

def sim_time_only(daily, q, zone, tps, wide=1.5):
    """B3 纯时间朋友: 宽SL, 无TP, 15根收盘全出。"""
    f = EN.fill_in_zone(daily, q, zone, max_bars=6)
    if f is None or f["fill_price"] is None:
        return None, None
    k0, px = f["fill_idx"], f["fill_price"]
    if k0 + 15 >= len(daily):
        return None, None
    atr_abs = px * 0.025
    try:
        from core.structure import atr_of
        a_ = atr_of(daily, k0) or 0
        if a_:
            atr_abs = a_
    except Exception:
        pass
    sl = zone["invalid_price"] - wide * atr_abs
    for k in range(k0 + 1, min(len(daily), k0 + 16)):
        if daily[k]["l"] <= sl:
            return ((sl / px - 1) * 100) - FEE, (k0, px)
    return ((daily[min(len(daily)-1, k0 + 15)]["c"] / px - 1) * 100) - FEE, (k0, px)

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
    if len(sel) < 10:
        return None
    ms = []
    for _ in range(iters):
        s = random.choices(sel, k=len(sel))
        ms.append(sum(s)/len(s))
    ms.sort()
    return [round(ms[int(0.025*len(ms))], 3), round(ms[int(0.975*len(ms))], 3)]

arms = {"B1_fastTP": [], "B2_delayedTP_wideSL": [], "B3_timeOnly_wideSL": []}
for code, daily, q, poi in ready:
    z = EN.entry_zone(poi, price=daily[q]["c"], invalid_price=poi["low"] * 0.97,
                      atr_pct=max(0.01, (daily[q]["h"] - daily[q]["l"]) / max(0.01, daily[q]["c"])))
    if z is None:
        continue
    tps = RK.structured_tp_sl(daily, q, z)
    if tps is None:
        continue
    d8 = daily[q]["t"]
    r1, _ = sim_b1(daily, q, z, tps)
    if r1 is not None:
        arms["B1_fastTP"].append((code, d8, r1))
    r2, _ = sim_delayed(daily, q, z, tps)
    if r2 is not None:
        arms["B2_delayedTP_wideSL"].append((code, d8, r2))
    r3, _ = sim_time_only(daily, q, z, tps)
    if r3 is not None:
        arms["B3_timeOnly_wideSL"].append((code, d8, r3))

random.seed(42)
out = {}
print("\n== 退出结构三臂消融 ==")
for k, arm in arms.items():
    out[k] = {"IS": stats(arm, False), "OOS": stats(arm, True), "OOS_ci": boot(arm, True), "n": len(arm)}
    print(f"  {k:22s}: IS={out[k]['IS']}")
    print(f"  {'':22s}  OOS={out[k]['OOS']} CI={out[k]['OOS_ci']}")
b2_oos = out["B2_delayedTP_wideSL"]["OOS"]; b1_oos = out["B1_fastTP"]["OOS"]; b3_oos = out["B3_timeOnly_wideSL"]["OOS"]
verdict = {"B2_beats_B1_avg": b2_oos.get("avg", -99) > b1_oos.get("avg", -99),
           "B2_beats_B1_pf": b2_oos.get("pf", 0) > b1_oos.get("pf", 0),
           "B3_beats_B1_avg": b3_oos.get("avg", -99) > b1_oos.get("avg", -99),
           "pool_targets_harmful": b3_oos.get("avg", -99) >= b2_oos.get("avg", -99)}
out["verdict"] = verdict
print("\n== 预注册判定 ==")
print(f"  B2(延迟TP+宽SL) > B1(快TP) avg: {verdict['B2_beats_B1_avg']} ({b2_oos.get('avg')} vs {b1_oos.get('avg')})")
print(f"  B2 > B1 PF: {verdict['B2_beats_B1_pf']} ({b2_oos.get('pf')} vs {b1_oos.get('pf')})")
print(f"  B3(纯时间) > B1 avg: {verdict['B3_beats_B1_avg']} ({b3_oos.get('avg')} vs {b1_oos.get('avg')})")
print(f"  → 池目标有害(时间臂>=池目标臂): {verdict['pool_targets_harmful']}")

json.dump(out, open(r"E:\test\smc_project\research\handover\V2退出结构三臂消融.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("\n已写 handover/V2退出结构三臂消融.json")
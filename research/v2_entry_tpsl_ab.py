# -*- coding: utf-8 -*-
"""V2 ITERATION 7/8 A/B: Entry Zone + 结构化TP/SL vs 骨架市价追入
用新引擎 READY 链(同迭代3)对比:
  A臂(骨架, 基线) = retest bar 次日开盘市价买, 持有15日收盘卖(迭代3同口径)
  B臂(Entry+TP/SL) = fill_in_zone 回踩 zone 成交, structured_tp_sl:
      SL 破位即出; TP1 到价减半仓; TP2 再减; TP3/15日收盘
两臂同 READY 信号集, 同成本, OOS 对比。
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

def pnl15(daily, i):
    if i + 16 >= len(daily):
        return None
    buy = daily[i + 1]["o"]
    sell = daily[i + 15]["c"]
    if buy <= 0:
        return None
    return (sell / buy - 1) * 100 - FEE

def sim_zone(daily, i, zone, tps):
    """B臂模拟: retest 决策点 i 后 max_bars=6 根内回踩 zone 成交 →
    SL 破位出; TP1 半仓; TP2 再减; TP3 或 15根收盘清仓。"""
    f = EN.fill_in_zone(daily, i, zone, max_bars=6)
    if f is None or f["fill_price"] is None:
        return None
    k0, px = f["fill_idx"], f["fill_price"]
    if k0 + 15 >= len(daily):
        return None
    sl, tp1, tp2, tp3 = tps["sl"], tps["tp1"], tps["tp2"], tps["tp3"]
    rem, cost_b, realised = 1.0, px, 0.0
    exited = False
    for k in range(k0 + 1, min(len(daily), k0 + 16)):
        b = daily[k]
        # SL 优先(保守)
        if b["l"] <= sl:
            realised += rem * ((sl / px - 1) * 100)
            rem = 0.0
            exited = True
            break
        if rem > 0.51 and b["h"] >= tp1:
            realised += 0.5 * ((tp1 / px - 1) * 100)
            rem -= 0.5
        if rem > 0.21 and b["h"] >= tp2:
            realised += 0.5 * ((tp2 / px - 1) * 100)
            rem -= 0.5
        if b["h"] >= tp3:
            realised += rem * ((tp3 / px - 1) * 100)
            rem = 0.0
            exited = True
            break
    if rem > 0:
        realised += rem * ((daily[min(len(daily) - 1, k0 + 15)]["c"] / px - 1) * 100)
    if not exited and rem > 0:
        pass
    return realised - FEE

ready = []  # (code, daily, i_ready, poi)
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

print(f"READY 链: {len(ready)}")
armA, armB = [], []
for code, daily, q, poi in ready:
    pA = pnl15(daily, q)
    if pA is None:
        continue
    armA.append((code, daily[q]["t"], pA))
    # B臂: entry zone + 结构化 TP/SL
    z = EN.entry_zone(poi, price=daily[q]["c"], invalid_price=poi["low"] * 0.97,
                      atr_pct=max(0.01, (daily[q]["h"] - daily[q]["l"]) / max(0.01, daily[q]["c"])))
    if z is None:
        continue
    tps = RK.structured_tp_sl(daily, q, z)
    if tps is None:
        continue
    pB = sim_zone(daily, q, z, tps)
    if pB is not None:
        armB.append((code, daily[q]["t"], pB))

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

random.seed(42)
out = {"A_skeleton": {"IS": stats(armA, False), "OOS": stats(armA, True), "OOS_ci": boot(armA, True)},
       "B_entry_tpsl": {"IS": stats(armB, False), "OOS": stats(armB, True), "OOS_ci": boot(armB, True)},
       "nA": len(armA), "nB": len(armB)}
print(f"\n== ITERATION 7/8 A/B ==")
for k in ("A_skeleton", "B_entry_tpsl"):
    v = out[k]
    print(f"  {k:14s}: IS={v['IS']}")
    print(f"  {'':14s}  OOS={v['OOS']} CI={v['OOS_ci']}")
b_oos = out["B_entry_tpsl"]["OOS"]; a_oos = out["A_skeleton"]["OOS"]
verdict = {"B_sample_ok": b_oos.get("n", 0) >= 50,
           "B_beats_A_avg": b_oos.get("avg", -99) > a_oos.get("avg", -99),
           "B_beats_A_pf": b_oos.get("pf", 0) > a_oos.get("pf", 0)}
verdict["entry_tpsl_improves"] = all(verdict.values())
out["verdict"] = verdict
print(f"\n样本: B>=50 {verdict['B_sample_ok']} | avg {b_oos.get('avg')}>{a_oos.get('avg')} {verdict['B_beats_A_avg']} | PF {b_oos.get('pf')}>{a_oos.get('pf')} {verdict['B_beats_A_pf']}")
print(f"→ Entry+TP/SL 引擎提升: {verdict['entry_tpsl_improves']}")

json.dump(out, open(r"E:\test\smc_project\research\handover\V2迭代7_8_EntryTPSL消融.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("已写 handover/V2迭代7_8_EntryTPSL消融.json")
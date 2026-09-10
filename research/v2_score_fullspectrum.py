# -*- coding: utf-8 -*-
"""TradeScore 全谱分桶单调性(放宽硬门重扫)
目的: 让 READY 链的低分桶(C/D)有样本, 验证完整四桶 OOS 单调性。
放宽: disp_min 50→30, pool_min 40→20(结构仍完整: sweep→reclaim→disp→shift→poi→retest)。
输出: 四桶 OOS avg/WR/PF + A vs D 差异 + bootstrap。
诚实面: 放宽门后链更松(候选多但质量摊薄), 验证的是'score 是否在全谱有区分度'。"""
import glob, io, json, os, random, sys
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.liquidity as LQ
import core.displacement as DS
import core.mss as MSS
import core.fvg_ob as FO
import core.entry as EN
import core.scoring as SC

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.20
DISP_MIN, POOL_MIN = 30, 20
files = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::5][:800]

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

trades = []
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
                                            dts = []
                                            try:
                                                dts = [(_dnum(daily[k]["t"]) - _dnum(daily[i]["t"])).days,
                                                       (_dnum(daily[m]["t"]) - _dnum(daily[k]["t"])).days,
                                                       (_dnum(daily[q]["t"]) - _dnum(daily[m]["t"])).days]
                                            except Exception:
                                                dts = []
                                            ts = SC.trade_score(s5, pools, dts, sc_disp, zone)
                                            p = sim_b3(daily, q, zone)
                                            if p is not None:
                                                trades.append((code, daily[q]["t"], p, ts["bucket"], ts["score"]))
                                            break
                                        if daily[q]["c"] < poi["low"] * 0.97:
                                            break
                                break
                        break
                elif daily[k]["c"] < pool * (1 - 2 * tol):
                    break

random.seed(42)
print(f"放宽门链: {len(trades)} 笔", flush=True)
buckets = ("A_80_100", "B_60_80", "C_40_60", "D_0_40")
res = {}
for bk in buckets:
    sel = [t[2] for t in trades if t[3] == bk and t[1] >= OOS]
    w = [x for x in sel if x > 0]; l_ = [x for x in sel if x <= 0]
    res[bk] = {"n": len(sel), "avg": round(sum(sel)/len(sel), 3) if sel else None,
               "wr": round(len(w)/len(sel), 3) if sel else None,
               "pf": round(sum(w)/abs(sum(l_)), 2) if l_ and sum(l_) != 0 else 99}
    print(f"  {bk}: {res[bk]}", flush=True)

# 完整四桶单调性(每个桶 n>=20; D桶链路硬性下限≈45分故结构性空, 如实记录)
valid = [res[bk]["avg"] for bk in buckets if res[bk]["n"] >= 20 and res[bk]["avg"] is not None]
mono = all(valid[j] >= valid[j+1] - 0.2 for j in range(len(valid)-1))
a_d = (res["A_80_100"]["avg"] - res["D_0_40"]["avg"]) if res["D_0_40"]["avg"] is not None else None
res["_verdict"] = {"A_B_C_monotone": mono and len(valid) >= 2,
                   "D_bucket_structurally_empty": res["D_0_40"]["n"] == 0,
                   "A_minus_D": round(a_d, 3) if a_d is not None else None}
print(f"\n有效桶(ABC)单调: {mono} | D桶结构性空: {res['_verdict']['D_bucket_structurally_empty']} | A-D差: {res['_verdict']['A_minus_D']}")
json.dump(res, open(r"E:\test\smc_project\research\handover\TradeScore全谱分桶.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("已写 handover/TradeScore全谱分桶.json")
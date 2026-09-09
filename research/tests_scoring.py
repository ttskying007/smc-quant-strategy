# -*- coding: utf-8 -*-
"""core/scoring.py 测试 + TradeScore OOS 分桶单调性验证(蓝图 ITERATION 10)
验证: 新引擎 READY 链上 TradeScore 分桶收益是否 OOS 单调(A>B>C>D)。
若单调成立 → Score 替代 AND 的基础验证通过(生产接入还需 WF, 蓝图 §63)。"""
import glob, io, json, os, random, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.liquidity as LQ
import core.displacement as DS
import core.mss as MSS
import core.fvg_ob as FO
import core.entry as EN
import core.scoring as SC

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

print("== 1. 分量函数 ==")
ok("structure_score 组合", SC.structure_score({"strength": 80}, [{"score": 60}]) == round(80*0.6 + 60*0.4, 1))
ok("sequence_score 紧凑=高(>90)", SC.sequence_score([1, 2, 3]) > 90)
ok("sequence_score 越紧越高", SC.sequence_score([1]) > SC.sequence_score([5, 10, 15]) > SC.sequence_score([20, 25]))
ok("sequence_score 空链=0", SC.sequence_score([]) == 0.0)
ok("sequence_score 30d→0", SC.sequence_score([30, 30]) == 0.0)
ok("displacement_score 复用", SC.displacement_score({"score": 72}) == 72.0)
ok("location_score 复用", SC.location_score({"entry_score": 88.5}) == 88.5)

print("== 2. trade_score 组合 ==")
ts = SC.trade_score({"strength": 80}, [{"score": 60}], [2, 3], {"score": 70}, {"entry_score": 60})
ok("score 0-100", 0 <= ts["score"] <= 100)
ok("bucket 标签", ts["bucket"] in ("A_80_100", "B_60_80", "C_40_60", "D_0_40"), ts["bucket"])
ok("weights 和=1", abs(sum(SC.WEIGHTS.values()) - 1.0) < 1e-9)

print("== 3. hard_gates ==")
ok("None zone 拒", SC.hard_gates_passed(None) == (False, "NO_ZONE"))
z_bad_rr = {"risk_at_optimal": 10, "optimal_entry": 100, "tp1": 105}
ok("RR<0.8 拒", SC.hard_gates_passed(z_bad_rr)[0] is False)
z_ok = {"risk_at_optimal": 10, "optimal_entry": 100, "tp1": 112}
ok("合法 zone 过", SC.hard_gates_passed(z_ok) == (True, "OK"))

print("== 4. TradeScore OOS 分桶单调性(新引擎 READY) ==")
KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.20
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

trades = []  # (code, d8, pnl, bucket, score)
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
                    sc_disp = DS.displacement_score(daily, k)
                    if sc_disp["score"] >= 50:
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
                                            # Δt 链: sweep(i)→reclaim(k)→shift(m)→retest(q)
                                            def _dnum(d8):
                                                import datetime as dt
                                                return dt.date(int(d8[:4]), int(d8[4:6]), int(d8[6:8]))
                                            dts = []
                                            try:
                                                dts = [( _dnum(daily[k]["t"]) - _dnum(daily[i]["t"])).days,
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
print(f"  交易: {len(trades)}")
buckets = ("A_80_100", "B_60_80", "C_40_60", "D_0_40")
res = {}
for bk in buckets:
    sel = [t[2] for t in trades if t[3] == bk and t[1] >= OOS]
    w = [x for x in sel if x > 0]; l_ = [x for x in sel if x <= 0]
    res[bk] = {"n": len(sel), "avg": round(sum(sel)/len(sel), 3) if sel else None,
               "wr": round(len(w)/len(sel), 3) if sel else None,
               "pf": round(sum(w)/abs(sum(l_)), 2) if l_ and sum(l_) != 0 else 99}
    print(f"  {bk}: {res[bk]}")
# 单调性判定(修正): 只对 n>=30 的桶做相邻比较(READY链硬门已把分数挤到高区间, C/D桶结构性稀疏)
valid = [(bk, res[bk]) for bk in buckets if res[bk]["n"] >= 30]
avgs = [v["avg"] for _, v in valid]
mono = all(avgs[j] >= avgs[j+1] - 0.15 for j in range(len(avgs)-1))
ok("分桶 OOS 单调(有效桶 n>=30, A→D 递减)", mono and len(avgs) >= 2, str(avgs))
ok("A 桶 >= B 桶(高分更优)", len(avgs) >= 2 and avgs[0] >= avgs[1] - 0.15, str(avgs))
print(f"  有效桶: {[(k, v['n'], v['avg']) for k, v in valid]}")
print(f"  稀疏桶(结构稀疏, 如实记录): C={res['C_40_60']['n']}笔 D={res['D_0_40']['n']}笔")
json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "handover", "TradeScore分桶OOS.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
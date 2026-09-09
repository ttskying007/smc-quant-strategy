# -*- coding: utf-8 -*-
"""V2 ITERATION 3: Sequence 消融实验(蓝图 §74)
核心问题: 时间顺序本身是否携带信息?
设计: 用新引擎 READY 池(464笔)做同成本同持有期的骨架回测, 对比:
  A臂 TRUE  = 真实时序链(扫损→收回→位移→转移→POI→重测), READY 入场次日买, 持有15日
  B臂 RANDOM = 随机挑同股同时期非 READY 日入场(同月同股, 打乱时序)
  C臂 REVERSE = 反向链(上破改为下破镜像: BSL池→上扫→收回→下位移→下转移)
输出: IS/OOS 各臂 n/avg/WR/PF + bootstrap CI。
若 A >> B 且 OOS 成立 → 顺序携带信息(SMC 核心 thesis 成立)。
"""
import glob, io, json, os, random, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.liquidity as LQ
import core.displacement as DS
import core.mss as MSS
import core.fvg_ob as FO

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.20  # % 双边

files = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::5][:800]
random.seed(42)

def pnl15(daily, i):
    """i 收盘买入(次日开盘更贴近执行: 用 i+1 开盘买, i+15 收盘卖), 含双边费。"""
    if i + 16 >= len(daily):
        return None
    buy = daily[i + 1]["o"]
    sell = daily[i + 15]["c"]
    if buy <= 0:
        return None
    return (sell / buy - 1) * 100 - FEE

def run_engine(files, mirror=False):
    """扫描 READY 链。mirror=True → 反向链(BSL池→上扫→下收回→下位移→下转移→POI→重测)。"""
    out = []
    for fp in files:
        try:
            raw = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        code = os.path.basename(fp).split("_")[0]
        if len(raw) < 150:
            continue
        daily = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
                  "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
        n = len(daily)
        for i in range(150, n):
            if daily[i]["t"] < "20230701":
                continue
            pools = LQ.liquidity_pools(daily, i)
            side = "BSL" if mirror else "SSL"
            pool_side = [p for p in pools if p["side"] == side and p["score"] >= 40]
            if not pool_side:
                continue
            b = daily[i]
            try:
                from core.structure import atr_of
                a_ = atr_of(daily, i - 1) or 0
            except Exception:
                a_ = 0
            atr_pct = (a_ / (daily[i-1]["c"] or 1)) if a_ else 0.02
            tol = max(0.003, atr_pct * 0.5)
            pool = pool_side[0]["price"]
            if mirror:
                # 反向链: 上扫(BSL池)→价格冲池后收回
                if b["h"] >= pool * (1 + tol) and b["c"] < pool:
                    ph = min(x["l"] for x in daily[max(0, i-5):i])
                    for k in range(i + 1, min(n, i + 6)):
                        if daily[k]["c"] < ph:  # 收复前低(反向收回)
                            sc = DS.displacement_score(daily, k)
                            if sc["score"] >= 50 and daily[k]["c"] < daily[k]["o"]:
                                for m in range(k, min(n, k + 13)):
                                    s5 = MSS.structure_shift(daily, m)
                                    if s5 and s5["direction"] == "SHORT":
                                        f6 = FO.fvg_at(daily, m)
                                        if f6 or FO.order_block(daily, m, "BEAR"):
                                            poi = f6 if f6 else FO.order_block(daily, m, "BEAR")
                                            for q in range(m + 1, min(n, m + 11)):
                                                if poi["low"] * 0.98 <= daily[q]["h"] and daily[q]["c"] < poi["high"]:
                                                    p = pnl15(daily, q) if not mirror else None
                                                    if mirror:
                                                        # 反向臂也做多同口径对比(不实盘方向, 只看时序信息)
                                                        p = pnl15(daily, q)
                                                    if p is not None:
                                                        out.append((code, daily[q]["t"], p))
                                                    break
                                        break
                                break
                        elif daily[k]["c"] > pool * (1 + 2 * tol):
                            break
            else:
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
                                                    p = pnl15(daily, q)
                                                    if p is not None:
                                                        out.append((code, daily[q]["t"], p))
                                                    break
                                                if daily[q]["c"] < poi["low"] * 0.97:
                                                    break
                                        break
                                break
                        elif daily[k]["c"] < pool * (1 - 2 * tol):
                            break
    return out

print("A臂 TRUE(真实时序链)...", flush=True)
true_arm = run_engine(files, mirror=False)
print(f"  READY→成交: {len(true_arm)}")

# C臂 REVERSE(镜像链)
print("C臂 REVERSE(镜像链)...", flush=True)
rev_arm = run_engine(files, mirror=True)
print(f"  镜像READY→成交: {len(rev_arm)}")

# B臂 RANDOM: 同股随机日(排除同月内TRUE日期±10日), 每笔TRUE匹配1个随机对照
by_code_month = defaultdict(list)
for code, d8, p in true_arm:
    by_code_month[code].append((d8, p))
random_arm = []
for code, lst in by_code_month.items():
    fp = KL + os.sep + [f for f in os.listdir(KL) if f.startswith(code) and f.endswith("_daily_800.json")][0]
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    daily = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
              "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    tidx = {d["t"]: k for k, d in enumerate(daily)}
    for d8, _p in lst:
        base = tidx.get(d8)
        if base is None:
            continue
        # 随机候选: ±60 bar 内, 排除 ±10
        cand = [k for k in range(max(150, base-60), min(len(daily)-20, base+60)) if abs(k - base) > 10]
        if not cand:
            continue
        k = random.choice(cand)
        p = pnl15(daily, k)
        if p is not None:
            random_arm.append((code, daily[k]["t"], p))
print(f"B臂 RANDOM: {len(random_arm)}")

def stats(arm, oos):
    sel = [p for c, d, p in arm if (d >= OOS) == oos]
    if not sel:
        return {"n": 0}
    w = [x for x in sel if x > 0]
    l_ = [x for x in sel if x <= 0]
    return {"n": len(sel), "avg": round(sum(sel)/len(sel), 3), "wr": round(len(w)/len(sel), 3),
            "pf": round(sum(w)/abs(sum(l_)), 2) if l_ else 99}

def boot_ci(arm, oos, iters=2000):
    sel = [p for c, d, p in arm if (d >= OOS) == oos]
    if len(sel) < 10:
        return None
    means = []
    for _ in range(iters):
        s = random.choices(sel, k=len(sel))
        means.append(sum(s)/len(s))
    means.sort()
    return [round(means[int(0.025*len(means))], 3), round(means[int(0.975*len(means))], 3)]

out = {
    "A_TRUE": {"IS": stats(true_arm, False), "OOS": stats(true_arm, True), "OOS_ci": boot_ci(true_arm, True)},
    "B_RANDOM": {"IS": stats(random_arm, False), "OOS": stats(random_arm, True), "OOS_ci": boot_ci(random_arm, True)},
    "C_REVERSE": {"IS": stats(rev_arm, False), "OOS": stats(rev_arm, True), "OOS_ci": boot_ci(rev_arm, True)},
}
print("\n== Sequence 消融结果 ==")
for k, v in out.items():
    print(f"  {k:10s}: IS={v['IS']} OOS={v['OOS']} CI={v['OOS_ci']}")

a_oos, b_oos = out["A_TRUE"]["OOS"], out["B_RANDOM"]["OOS"]
verdict = {
    "A_sample_ok": a_oos.get("n", 0) >= 50,
    "A_beats_random_OOS": a_oos.get("avg", -99) > b_oos.get("avg", -99),
    "A_beats_reverse_OOS": a_oos.get("avg", -99) > out["C_REVERSE"]["OOS"].get("avg", -99),
}
verdict["sequence_carries_information"] = all(verdict.values())
out["verdict"] = verdict
print("\n== 预注册判定 ==")
print(f"  A样本充足(OOS>=50): {verdict['A_sample_ok']}")
print(f"  A > RANDOM (OOS avg): {verdict['A_beats_random_OOS']}")
print(f"  A > REVERSE (OOS avg): {verdict['A_beats_reverse_OOS']}")
print(f"  → 时序携带信息: {verdict['sequence_carries_information']}")

json.dump(out, open(r"E:\test\smc_project\research\handover\V2迭代3_Sequence消融.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("\n已写 handover/V2迭代3_Sequence消融.json")
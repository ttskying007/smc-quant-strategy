# -*- coding: utf-8 -*-
"""P0-4: Sequence Family Database(阶段消融, V3 审计§七/Phase C)
V3核心研究问题: FSM 解决了"能记录因果顺序", 本实验解决"【哪些顺序真的有收益意义】"。

变体族(全部 OOS 20250701+, 800股抽样, 统一 setup_exit 退出):
  A_full   : LIQ→SWEEP→RECLAIM→DISP→SHIFT→POI→RETEST (完整链, 基准)
  B_no_reclaim: SWEEP→DISP→SHIFT→POI→RETEST (跳过 RECLAIM —— 收复是否携带独立信息?)
  C_trunc  : LIQ→SWEEP→RECLAIM→DISP (链在前半截断 —— 后半结构是否必要?)
  D_poi_only: DISP→POI→RETEST (无 liquidity/sweep 先导 —— 流动性链是否必要?)
  E_reverse: DISP→SHIFT→SWEEP→POI→RETEST (顺序反转对照 —— 顺序本身的信息量)
每族统计: N/WR/Avg/PF/MFE/MAE + 5D/10D/20D 前向收益。
预注册判定线:
  A vs B: |Δavg|<0.5pp → RECLAIM 不携带独立信息(可简化); Δ>1pp → RECLAIM 有效
  A vs C: C 显著更差(>1pp) → 后半结构(SHIFT/POI/RETEST)必要
  A vs D: D 显著更差(>1pp) → 流动性先导链必要(纯形态 POI 无 alpha)
  A vs E: E 显著更差 → 顺序携带信息(Ture>>Reverse 的 §74 检验)
  任一结论 n<30 → UNKNOWN(不宣称)。
输出: handover/SequenceFamily数据库.json"""
import glob, io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.liquidity as LQ
import core.displacement as DSP
import core.mss as MSS
import core.fvg_ob as FO
from core.structure import atr_of
from core.entry import fill_in_zone
from core.setup_exit import settle_setup

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.2
POOL_MIN, DISP_MIN, RETEST_BARS = 40, 50, 8

FILES = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::5][:800]

def variants_at(daily, i):
    """决策点 i 的五变体判定。返回 {variant: setup_dict or None}(setup 含 poi/invalid)。"""
    out = {"A_full": None, "B_no_reclaim": None, "C_trunc": None, "D_poi_only": None, "E_reverse": None}
    if i < 60:
        return out
    atr = atr_of(daily, i - 1) or 0
    atr_pct = atr / (daily[i - 1]["c"] or 1) if atr else 0.02
    tol = max(0.003, atr_pct * 0.5)
    w0 = max(60, i - 40)
    pools = LQ.liquidity_pools(daily, w0 + 1)
    ssl = [p for p in pools if p["side"] == "SSL" and p["score"] >= POOL_MIN]
    n = len(daily)

    def poi_after(k_from, k_to):
        """找 FVG/OB POI(窗口内最早)。"""
        for k in range(k_from, min(n, k_to)):
            f = FO.fvg_at(daily, k)
            if f:
                return k, {"type": "FVG", "low": f["low"], "high": f["high"], "mid": f["mid"]}
            o_ = FO.order_block(daily, k, "BULL")
            if o_:
                return k, {"type": "OB", "low": o_["low"], "high": o_["high"], "mid": o_["mid"]}
        return None, None

    def retest_after(poi, k_from, bars=RETEST_BARS):
        for k in range(k_from + 1, min(n, k_from + 1 + bars)):
            b = daily[k]
            if b["c"] < poi["low"] * 0.97:
                return None
            if poi["low"] <= b["l"] <= poi["high"] * 1.02:
                return k
        return None

    # ---- A_full(完整链, 与 run_sequence_v2 同语义) ----
    if ssl:
        pool = ssl[0]
        sw_i = None
        for k in range(w0 + 2, i + 1):
            b = daily[k]
            if b["l"] <= pool["price"] * (1 - tol) and b["c"] > pool["price"]:
                sw_i = k
                break
            if b["c"] < pool["price"] * (1 - 2 * tol):
                break
        if sw_i is not None:
            ph = max(x["h"] for x in daily[max(0, sw_i - 5):sw_i])
            rc_i = None
            for k in range(sw_i + 1, min(n, sw_i + 6)):
                if daily[k]["c"] > ph:
                    rc_i = k
                    break
                if daily[k]["c"] < pool["price"] * (1 - 2 * tol):
                    break
            if rc_i is not None:
                # DISP
                dp_i = None
                for k in range(rc_i, min(n, rc_i + 6)):
                    sc = DSP.displacement_score(daily, k)
                    if sc["score"] >= DISP_MIN and daily[k]["c"] > daily[k]["o"]:
                        dp_i = k
                        break
                if dp_i is not None:
                    # C_trunc: 链到 DISP 为止(不要求 SHIFT/POI/RETEST)
                    out["C_trunc"] = {"poi": {"type": "NONE", "low": min(x["l"] for x in daily[max(0, i-5):i+1]),
                                              "high": min(x["l"] for x in daily[max(0, i-5):i+1]) * 1.03,
                                              "mid": min(x["l"] for x in daily[max(0, i-5):i+1]) * 1.015},
                                      "truncated": True}
                    # SHIFT
                    sh_i = None
                    for k in range(dp_i, min(n, dp_i + 13)):
                        s5 = MSS.structure_shift(daily, k)
                        if s5 and s5["direction"] == "LONG":
                            sh_i = k
                            break
                    if sh_i is not None:
                        pk, poi = poi_after(sh_i, sh_i + 4)
                        if pk is not None:
                            rt_i = retest_after(poi, pk)
                            if rt_i is not None:
                                out["A_full"] = {"poi": poi}
                            # B_no_reclaim: 无 RECLAIM 要求 —— 用 SWEEP 后直接 DISP
                        # B: sweep→disp(跳 reclaim)
                        dp2 = None
                        for k in range(sw_i, min(n, sw_i + 8)):
                            sc = DSP.displacement_score(daily, k)
                            if sc["score"] >= DISP_MIN and daily[k]["c"] > daily[k]["o"]:
                                dp2 = k
                                break
                        if dp2 is not None:
                            sh2 = None
                            for k in range(dp2, min(n, dp2 + 13)):
                                s5 = MSS.structure_shift(daily, k)
                                if s5 and s5["direction"] == "LONG":
                                    sh2 = k
                                    break
                            if sh2 is not None:
                                pk2, poi2 = poi_after(sh2, sh2 + 4)
                                if pk2 is not None:
                                    rt2 = retest_after(poi2, pk2)
                                    if rt2 is not None:
                                        out["B_no_reclaim"] = {"poi": poi2}
                            # E_reverse: 先有 shift/POI 再出现 sweep(顺序反转对照)
                            rev_sw = None
                            for k in range(max(60, i - 40), i + 1):
                                if daily[k]["l"] <= min(x["l"] for x in daily[max(0, k-20):k]) * (1 - tol) and daily[k]["c"] > min(x["l"] for x in daily[max(0, k-20):k]):
                                    rev_sw = k
                                    break
                            if rev_sw is not None and sh2 is not None and rev_sw > sh2:
                                pk3, poi3 = poi_after(sh2, sh2 + 4)
                                if pk3 is not None:
                                    out["E_reverse"] = {"poi": poi3}
    # ---- D_poi_only: 无 liquidity/sweep 先导, 仅形态 POI+RETEST ----
    pk4, poi4 = poi_after(max(60, i - 15), i + 1)
    if pk4 is not None:
        rt4 = retest_after(poi4, pk4)
        if rt4 is not None:
            out["D_poi_only"] = {"poi": poi4}
    return out

fam = {v: [] for v in ("A_full", "B_no_reclaim", "C_trunc", "D_poi_only", "E_reverse")}
t0 = time.time()
for fp in FILES:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    if len(raw) < 200:
        continue
    code = os.path.basename(fp).split("_")[0]
    daily = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
              "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    n = len(daily)
    for i in range(150, n - 25):
        if daily[i]["t"] < OOS:
            continue
        vs = variants_at(daily, i)
        d8 = daily[i]["t"]
        for vname, s in vs.items():
            if s is None:
                continue
            if vname == "C_trunc":
                # 截断链: 直接 zone 撮合(近5bar低带)
                lo = s["poi"]["low"]
                zone = {"zone_low": lo, "zone_high": s["poi"]["high"], "invalid_price": lo * 0.97,
                        "optimal_entry": s["poi"]["mid"]}
                fill = fill_in_zone(daily, i, zone, max_bars=5, fill_mode="STRICT_LIMIT")
                if fill is None or fill.get("fill_price") is None:
                    continue
                fi, fpx = fill["fill_idx"], fill["fill_price"]
                from core.setup_exit import settle_from_record
                res = settle_from_record(daily, fi, fpx, zone["invalid_price"], fee_pct=FEE)
                if res["status"] in ("SL", "TP", "TIME"):
                    fam[vname].append((d8, res["ret_pct"]))
            else:
                res = settle_setup(daily, i, {"poi": s["poi"]}, fee_pct=FEE)
                if res and res["status"] in ("SL", "TP", "TIME"):
                    fam[vname].append((d8, res["ret_pct"]))

def stats(pnl):
    if not pnl:
        return {"n": 0}
    vals = [p for _, p in pnl]
    w = sum(x for x in vals if x > 0)
    l_ = abs(sum(x for x in vals if x <= 0))
    return {"n": len(vals), "avg": round(sum(vals) / len(vals), 3),
            "wr": round(len([x for x in vals if x > 0]) / len(vals) * 100, 1),
            "pf": round(w / l_, 2) if l_ > 0 else None}

S = {v: stats(fam[v]) for v in fam}
a, b, c, d_, e = (S["A_full"], S["B_no_reclaim"], S["C_trunc"], S["D_poi_only"], S["E_reverse"])

def delta(x, y):
    if x.get("avg") is None or y.get("avg") is None:
        return None
    return round(y["avg"] - x["avg"], 3)

tests = {
    "A_vs_B(收复RECLAIM独立信息)": {"delta": delta(a, b), "n_b": b["n"],
        "verdict": ("RECLAIM有效" if delta(a, b) is not None and delta(a, b) >= 1.0 and b["n"] >= 30
                    else ("RECLAIM可简化" if delta(a, b) is not None and abs(delta(a, b)) < 0.5 and b["n"] >= 30
                          else "UNKNOWN(样本不足)"))},
    "A_vs_C(后半结构必要性)": {"delta": delta(a, c), "n_c": c["n"],
        "verdict": ("后半结构必要" if delta(a, c) is not None and delta(a, c) >= 1.0 and c["n"] >= 30
                    else ("后半可简化" if delta(a, c) is not None and abs(delta(a, c)) < 0.5 and c["n"] >= 30
                          else "UNKNOWN(样本不足)"))},
    "A_vs_D(流动性先导必要性)": {"delta": delta(a, d_), "n_d": d_["n"],
        "verdict": ("流动性链必要" if delta(a, d_) is not None and delta(a, d_) >= 1.0 and d_["n"] >= 30
                    else ("纯形态POI无独立alpha" if delta(a, d_) is not None and abs(delta(a, d_)) < 0.5 and d_["n"] >= 30
                          else "UNKNOWN(样本不足)"))},
    "A_vs_E(顺序信息量检验§74)": {"delta": delta(a, e), "n_e": e["n"],
        "verdict": ("顺序携带信息" if delta(a, e) is not None and delta(a, e) >= 1.0 and e["n"] >= 30
                    else ("顺序不携带信息" if delta(a, e) is not None and abs(delta(a, e)) < 0.5 and e["n"] >= 30
                          else "UNKNOWN(样本不足)"))},
}
out = {"window": f"OOS {OOS}+ 800股抽样", "families": S, "tests": tests,
       "runtime_s": round(time.time() - t0)}
for v, s in S.items():
    print(f"  {v:14s}: {s}")
print()
for k, t in tests.items():
    print(f"  {k}: Δ={t['delta']}pp → {t['verdict']}")
json.dump(out, open(r"E:\test\smc_project\research\handover\SequenceFamily数据库.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("已写 handover/SequenceFamily数据库.json")
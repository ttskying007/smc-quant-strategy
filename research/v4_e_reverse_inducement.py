# -*- coding: utf-8 -*-
"""v4_e_reverse_inducement.py —— E_reverse 机理研究(V3-D, 预注册)
背景: Family DB E_reverse(212笔 PRELIMINARY) avg +2.62 > A_full +1.41 —— 反常。
机理假设: "晚扫" = 位移后扫流动性【扫入 POI】(SMC inducement) → 更深折价入场。
  若机理成立 → 不是"顺序反转携带信息"那么神秘, 而是【入场价更优】。

E_reverse_v2 独立定义(决策时点 i 无前视):
  ① SHIFT: [i-40, i] 内存在 LONG structure shift (sh_i)
  ② POI: shift 后 13bar 内形成 BULL FVG/OB (pk, poi)
  ③ 晚扫入 POI: (pk, i] 内某 bar: low <= poi.low(触及/刺穿 POI 下沿)
      且 close > poi.low(收回) —— sweep-into-zone
  ④ 挂单: 从 i 起 STRICT_LIMIT 撮 POI 区(5bar 窗)
  ⑤ 退出: settle_setup 单源(SL=invalid-1.5ATR/TP3R/TIME15)

对照: A_full(同 universe/窗口/退出, Family DB 锚 2201笔 +1.41)。
诊断: E_rev2 记录 fill 相对 poi.mid 的折价深度 discount_pct + MFE/MAE。
预注册判定:
  R1 样本: n ≥ 300 → 充足(旧 E_reverse 仅 212)
  R2 机理: E_rev2 平均折价 > 1.5%(扫入显著深于区中值) 且 MAE(E_rev2) < MAE(A_full 同法算)
  R3 优势: Δavg(E_rev2 − A_full) > +0.5pp → 诱敌晚扫族候选新 Family;
           |Δ|<0.5 → 顺序反转中性; < −0.5 → 晚扫劣
  任一 n<30 → UNKNOWN。
输出: handover/V4_E_reverse机理.json"""
import glob, io, json, os, random, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.mss as MSS
import core.fvg_ob as FO
from core.entry import fill_in_zone
from core.setup_exit import settle_setup
from core.structure import atr_of

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.2
FILES = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::2][:2000]   # 与 Family DB 同universe

def variants_at(daily, i):
    """返回 {A_full, E_rev2} 两变体(同决策点并行检测)。"""
    out = {"A_full": None, "E_rev2": None}
    n = len(daily)
    if i < 60:
        return out
    atr = atr_of(daily, i - 1) or 0
    atr_pct = atr / (daily[i - 1]["c"] or 1) if atr else 0.02
    tol = max(0.003, atr_pct * 0.5)

    def poi_after(k_from, k_to):
        for k in range(k_from, min(n, k_to)):
            f = FO.fvg_at(daily, k)
            if f:
                return k, {"type": "FVG", "low": f["low"], "high": f["high"], "mid": f["mid"]}
            o_ = FO.order_block(daily, k, "BULL")
            if o_:
                return k, {"type": "OB", "low": o_["low"], "high": o_["high"], "mid": o_["mid"]}
        return None, None

    # ---- E_rev2: shift → POI → 晚扫入POI(触及下沿+收回) ----
    sh = None
    for k in range(max(60, i - 40), i + 1):
        s5 = MSS.structure_shift(daily, k)
        if s5 and s5["direction"] == "LONG":
            sh = k
            break
    if sh is not None:
        pk, poi = poi_after(sh, sh + 13)
        if pk is not None and pk < i:
            swept = False
            for k in range(pk + 1, i + 1):
                b = daily[k]
                if b["l"] <= poi["low"] and b["c"] > poi["low"]:
                    swept = True          # 扫入 POI 且收回(决策时点已完成)
                    break
                if b["c"] < poi["low"] * 0.97:
                    swept = False          # POI 已失效(跌破过深)
                    break
            if swept:
                out["E_rev2"] = {"poi": poi, "pk": pk}
    # ---- A_full(与 Family DB 同语义复刻, 决策点内完成链) ----
    import core.liquidity as LQ
    import core.displacement as DSP
    w0 = max(60, i - 40)
    pools = LQ.liquidity_pools(daily, w0 + 1)
    ssl = [p for p in pools if p["side"] == "SSL" and p["score"] >= 40]
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
                dp_i = None
                for k in range(rc_i, min(n, rc_i + 6)):
                    sc = DSP.displacement_score(daily, k)
                    if sc["score"] >= 50 and daily[k]["c"] > daily[k]["o"]:
                        dp_i = k
                        break
                if dp_i is not None:
                    sh2 = None
                    for k in range(dp_i, min(n, dp_i + 13)):
                        s5 = MSS.structure_shift(daily, k)
                        if s5 and s5["direction"] == "LONG":
                            sh2 = k
                            break
                    if sh2 is not None:
                        pk2, poi2 = poi_after(sh2, sh2 + 4)
                        if pk2 is not None:
                            for q in range(pk2 + 1, min(n, pk2 + 9)):
                                b = daily[q]
                                if b["c"] < poi2["low"] * 0.97:
                                    break
                                if poi2["low"] <= b["l"] <= poi2["high"] * 1.02:
                                    out["A_full"] = {"poi": poi2}
                                    break
    return out

def mfe_mae(daily, fi, exit_idx, fpx):
    """成交到退出间的 MFE/MAE(相对成交价%)。"""
    hi = max(daily[k]["h"] for k in range(fi, exit_idx + 1))
    lo = min(daily[k]["l"] for k in range(fi, exit_idx + 1))
    return (hi / fpx - 1) * 100, (lo / fpx - 1) * 100

fam = {"A_full": [], "E_rev2": []}
disc = []          # E_rev2 折价深度(fill 相对 poi.mid)
mfeA, maeA, mfeE, maeE = [], [], [], []
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
            res = settle_setup(daily, i, s, fee_pct=FEE)
            if res and res["status"] in ("SL", "TP", "TIME"):
                fam[vname].append((d8, res["ret_pct"]))
                # MFE/MAE(需 fill 信息: settle_setup 无 fill_idx → 用近似: 次日开盘)
                # 为诊断一致性, 两侧同法: i+1 开盘为基准 fill
                if i + 1 < n:
                    mfe, mae = mfe_mae(daily, i + 1, min(i + 16, n - 1), daily[i + 1]["o"])
                    (mfeA if vname == "A_full" else mfeE).append(mfe)
                    (maeA if vname == "A_full" else maeE).append(mae)
                if vname == "E_rev2":
                    zone_mid = s["poi"]["mid"]
                    zone = {"zone_low": s["poi"]["low"], "zone_high": s["poi"]["high"],
                            "invalid_price": s["poi"]["low"] * 0.97,
                            "optimal_entry": zone_mid}
                    fill = fill_in_zone(daily, i, zone, max_bars=5, fill_mode="STRICT_LIMIT")
                    if fill and fill.get("fill_price"):
                        disc.append((zone_mid - fill["fill_price"]) / zone_mid * 100)

def stats(pnl):
    if not pnl:
        return {"n": 0}
    vals = [p for _, p in pnl]
    w = sum(x for x in vals if x > 0)
    l_ = abs(sum(x for x in vals if x <= 0))
    return {"n": len(vals), "avg": round(sum(vals) / len(vals), 3),
            "wr": round(len([x for x in vals if x > 0]) / len(vals) * 100, 1),
            "pf": round(w / l_, 2) if l_ > 0 else None}

def boot_ci(pnl, iters=2000, seed=7):
    random.seed(seed)
    vals = [p for _, p in pnl]
    if len(vals) < 10:
        return None
    means = sorted(sum(random.choices(vals, k=len(vals))) / len(vals) for _ in range(iters))
    return [round(means[int(0.025 * len(means))], 3), round(means[int(0.975 * len(means))], 3)]

S = {v: stats(fam[v]) for v in fam}
avg_disc = round(sum(disc) / len(disc), 3) if disc else None
mA = {"mfe": round(sum(mfeA) / len(mfeA), 2) if mfeA else None,
      "mae": round(sum(maeA) / len(maeA), 2) if maeA else None}
mE = {"mfe": round(sum(mfeE) / len(mfeE), 2) if mfeE else None,
      "mae": round(sum(maeE) / len(maeE), 2) if maeE else None}
delta = round(S["E_rev2"]["avg"] - S["A_full"]["avg"], 3) if S["E_rev2"].get("avg") is not None and S["A_full"].get("avg") is not None else None

verdict = {
    "R1_样本充足(n>=300)": S["E_rev2"]["n"] >= 300,
    "R2_折价深(>1.5%)且MAE更小": bool(avg_disc and avg_disc > 1.5
                                     and mE["mae"] is not None and mA["mae"] is not None
                                     and mE["mae"] > mA["mae"]),
    "R3_Δavg>0.5pp(晚扫优)": delta is not None and delta > 0.5,
    "R3_中性(|Δ|<0.5)": delta is not None and abs(delta) < 0.5,
    "R3_晚扫劣(<-0.5)": delta is not None and delta < -0.5,
}
out = {"window": f"OOS {OOS}+ 全市场[::2][:2000] 与FamilyDB同universe",
       "A_full": {**S["A_full"], "mfe_mae": mA, "oos_ci": boot_ci(fam["A_full"])},
       "E_rev2": {**S["E_rev2"], "mfe_mae": mE, "oos_ci": boot_ci(fam["E_rev2"]),
                  "avg_discount_pct_at_fill": avg_disc, "n_discount": len(disc)},
       "delta_E_rev2_minus_A_full": delta,
       "preregistered": verdict,
       "mechanism": "晚扫=sweep-into-POI(inducement): 更深折价入场假设",
       "runtime_s": round(time.time() - t0)}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_E_reverse机理.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"A_full : {S['A_full']}  MFE/MAE={mA}")
print(f"E_rev2 : {S['E_rev2']}  MFE/MAE={mE} 折价={avg_disc}%")
print(f"Δ(E_rev2−A_full) = {delta}pp")
print("预注册:", json.dumps(verdict, ensure_ascii=False))
print("已写 handover/V4_E_reverse机理.json")
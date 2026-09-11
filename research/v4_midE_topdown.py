# -*- coding: utf-8 -*-
"""v4_midE_topdown.py —— mid-E 峰的第二假说检验: 档内净值效应 vs 幸存者逆向选择(预注册 #33)
背景回顾:
  §17 mid 峰双机理: M1 跳过(过热 fill 率低) + 幸存者逆向选择(挂得进的偏弱)
  §32 E 档位仓量化: E≥0.54 段赢亏比 2.9:1(不对称健康)
剩余矛盾: §17 说 high 的幸存成交偏弱(逆向选择), §32 说 high 档赢亏比最健康 —— 两说冲突?
假说: 不冲突 —— §32 是**档位聚合**(时序内 E 决定仓位), §17 是**档内横截面**(同档内成交 vs 未成交)。
检验(预注册):
  N1 档内"成交子集 vs 尝试全集"的 avg 差随 E 档的变化(横截面逆向选择强度)
  N2 若 high 档 [成交avg − 全集avg] 差距 > mid 档差距 → §17 逆向选择确证(与 §32 不矛盾)
  N3 若差距在各档相近 → 逆向选择不是 mid 峰主因, §17 修正
方法: 复用 §17 机理实验框架(mid_e_mechanism), 增加"尝试全集收益"(未成交的用 5bar 后追价近似)。
简化: 尝试全集收益 = 全部 attempted 在 T+5 开盘追买的收益(无论是否成交, 代表"想买就能买")。"""
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
from core.setup_exit import settle_setup

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
FEE = 0.2
E_HIST = {d["d8"]: d.get("e") for d in json.load(open(
    r"E:\test\smc_project\research\handover\escore_history_full.json", encoding="utf-8")
).get("days", []) if d.get("e") is not None}
Q33, Q67 = 0.4559, 0.5562
def band(e):
    return None if e is None else ("low" if e <= Q33 else "mid" if e <= Q67 else "high")

FILES = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::2][:2000]

def a_full_poi(daily, i):
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
            return None
    if sw_i is None:
        return None
    ph = max(x["h"] for x in daily[max(0, sw_i - 5):sw_i])
    rc_i = None
    for k in range(sw_i + 1, min(n, sw_i + 6)):
        if daily[k]["c"] > ph:
            rc_i = k
            break
        if daily[k]["c"] < pool["price"] * (1 - 2 * tol):
            return None
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
        p = f if f else FO.order_block(daily, k, "BULL")
        if p:
            return p
    return None

stats = defaultdict(lambda: {"filled": [], "chase": []})
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
        # 成交臂(挂限价单)
        fill = fill_in_zone(daily, i, zone, max_bars=5, fill_mode="STRICT_LIMIT")
        if fill and fill.get("fill_price"):
            r = settle_setup(daily, fill["fill_idx"], {"poi": poi}, fee_pct=FEE)
            if r and r["status"] in ("SL", "TP", "TIME"):
                stats[bd]["filled"].append(r["ret_pct"])
        # 追买臂(全集近似: T+5 开盘市价买, 代表"想买就能买")
        j = min(i + 5, n - 16)
        if j > i and j + 15 < n and daily[j + 1]["o"] > 0:
            px = daily[j + 1]["o"]
            atr = atr_of(daily, j) or px * 0.025
            slp = zone["invalid_price"] - 1.5 * atr
            ret = None
            for k in range(j + 2, min(n, j + 16)):
                if daily[k]["l"] <= slp:
                    ret = (slp / px - 1) * 100 - FEE
                    break
            if ret is None:
                ret = (daily[min(n - 1, j + 15)]["c"] / px - 1) * 100 - FEE
            stats[bd]["chase"].append(ret)
print(f"{time.time()-t0:.0f}s")
out = {}
gaps = {}
for bd in ("low", "mid", "high"):
    f = stats[bd]["filled"]; c = stats[bd]["chase"]
    fa = round(sum(f) / len(f), 3) if f else None
    ca = round(sum(c) / len(c), 3) if c else None
    out[bd] = {"filled_n": len(f), "filled_avg": fa, "chase_n": len(c), "chase_avg": ca}
    if fa is not None and ca is not None:
        gaps[bd] = round(fa - ca, 3)     # 正=成交优于追买(限价单价值); 档间比较=逆向选择强度
hi = gaps.get("high"); mi = gaps.get("mid")
verdict = {
    "N2_high档逆向选择更强(high gap < mid gap − 1pp)": bool(
        hi is not None and mi is not None and hi < mi - 1.0),
    "N3_差距各档相近(逆向选择非主因)": None,
    "gaps_filled_minus_chase": gaps,
    "note": "gap=成交avg−追买avg; high 的 gap 若显著小于 mid → high 幸存成交的逆向选择确证",
}
verdict["N3_差距各档相近(逆向选择非主因)"] = not verdict["N2_high档逆向选择更强(high gap < mid gap − 1pp)"]
out["_preregistered"] = verdict
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_midE逆向选择.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=1))
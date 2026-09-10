# -*- coding: utf-8 -*-
"""F7 / V2 ITERATION 4: Multi-TF Parent/Child 事件链实验(数据可行性受限版)
蓝图 §23-26: Multi-TF 从"条件"升级为"角色": HTF=Context / MTF=Structure / LTF=Setup。

数据现实(2026-09-12 更新): 60m 缓存已扩至 2026-03-09→2026-09-04(9119 文件, 持续更新中)。
D1/60m 重叠窗 = 2026-03→2026-09 ~5 个月(原 2 个月); 15m 仍至 2026-07。
验收线(冻结): n<30 UNKNOWN / 30-100 PRELIMINARY / ≥100 VALIDATION / ≥200 STRONG。

实验设计(单一假设, 预注册):
  假设: D1 决策点的 READY 信号, 若同日 60m 图上有"收复完成"(子链 RECLAIMED 以上),
        则 15m 图上 POI 重测的入场时点更优(入场离失效位更近) —— Parent(D1 READY)
        → Child(60m 结构确认) → Entry(15m 重测) 三层角色链携带增量信息。
  对照臂:
    A. D1-READY only(基线, B3 退出)
    B. D1-READY + 60m 同窗确认(Parent/Child 链)
  判定线: B 的 OOS(2026-04后) avg 比 A 高 ≥1.0pp → MTF 角色链携带增量信息;
    |Δ|<1.0pp 或 B 样本不足以确认 → 数据窗不足, 结论=待更长缓存(诚实负/未知)。
"""
import glob, io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.sequence import run_sequence_v2
from core.entry import fill_in_zone

D1_KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
M60_KL = r"E:\test\smc_project\hermes\kline_cache_60min"
M15_KL = r"E:\test\smc_project\hermes\kline_cache_15min"
FEE = 0.20
WIN_START = "20260401"   # 60m/15m 重叠窗

def load60(code):
    for suf in ("_SZ", "_SH"):
        fp = os.path.join(M60_KL, f"{code}{suf}_60min_500.json")
        if os.path.exists(fp):
            raw = json.load(open(fp, encoding="utf-8"))
            return [{"t": str(b.get("t"))[:12], "d": str(b.get("t"))[:8],
                     "o": float(b["o"]), "h": float(b["h"]), "l": float(b["l"]),
                     "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    return None

def load15(code):
    for suf in ("_SZ", "_SH"):
        fp = os.path.join(M15_KL, f"{code}{suf}_15min_800.json")
        if os.path.exists(fp):
            raw = json.load(open(fp, encoding="utf-8"))
            return [{"t": str(b.get("t"))[:12], "d": str(b.get("d") or b.get("t"))[:8],
                     "o": float(b["o"]), "h": float(b["h"]), "l": float(b["l"]),
                     "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    return None

files = sorted(glob.glob(D1_KL + os.sep + "*_daily_800.json"))[::2][:2000]   # 60m 覆盖广→扩样本([::5][:400]→[::2][:2000])
armA, armB = [], []
n_ready = n_conf = 0
t0 = time.time()

for fp in files:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    if len(raw) < 200:
        continue
    code = os.path.basename(fp).split("_")[0]
    daily = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
              "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    k60 = load60(code)
    n = len(daily)
    for i in range(150, n - 20):
        d8 = daily[i]["t"]
        if d8 < WIN_START:
            continue
        m = run_sequence_v2(daily, i, symbol=code)
        if m.setup() is None:
            continue
        n_ready += 1
        # 回测基线臂 A(B3 退出, 与 B1 SHADOW 同口径)
        setup = m.setup()
        poi = setup["poi"]
        zone = {"zone_low": poi["low"], "zone_high": poi["high"], "invalid_price": poi["low"] * 0.97,
                "optimal_entry": poi["mid"]}
        fill = fill_in_zone(daily, i, zone, max_bars=5, fill_mode="STRICT_LIMIT")
        if fill is None or fill.get("fill_price") is None:
            continue
        fi, fpx = fill["fill_idx"], fill["fill_price"]
        from core.structure import atr_of
        atr = atr_of(daily, fi - 1) or 0.02 * fpx
        slp = zone["invalid_price"] - 1.5 * atr
        ret = None
        for k in range(fi + 1, min(n, fi + 16)):
            b = daily[k]
            if b["l"] <= slp:
                ret = (slp / fpx - 1) * 100 - FEE
                break
            if k == min(n - 1, fi + 15):
                ret = (b["c"] / fpx - 1) * 100 - FEE
        if ret is None:
            continue
        armA.append((d8, ret))
        # 臂 B: 同日 60m 子链确认 —— 60m 图上该日之前的最近 8 根内出现"低点收复"(l<prev_min 且 c>prev_min)
        if k60 is None:
            continue
        d8_key = d8
        bars_today = [b for b in k60 if b["d"] <= d8_key][-9:]
        if len(bars_today) < 9:
            continue
        prev8 = bars_today[:-1]
        prev_min = min(x["l"] for x in prev8)
        confirmed = any(x["l"] < prev_min and x["c"] > prev_min for x in [bars_today[-1]])
        if confirmed:
            n_conf += 1
            armB.append((d8, ret))

def stats(pnl):
    if not pnl:
        return {"n": 0}
    w = sum(x for _, x in pnl if x > 0); l_ = abs(sum(x for _, x in pnl if x <= 0))
    return {"n": len(pnl), "avg": round(sum(x for _, x in pnl) / len(pnl), 3),
            "pf": round(w / l_, 2) if l_ > 0 else 99.0}

sA, sB = stats(armA), stats(armB)
delta = round(sB.get("avg", 0) - sA.get("avg", 0), 3) if sB.get("avg") is not None and sA.get("avg") is not None else None
verdict = ("MTF 链携带增量信息" if delta is not None and delta >= 1.0 and sB.get("n", 0) >= 30
           else ("MTF 链反向(需警惕)" if delta is not None and delta <= -1.0 and sB.get("n", 0) >= 30
                 else "数据窗不足/差异不显著 —— 结论: 待更长缓存(诚实未知)"))
out = {"window": "2026-03→2026-09(60m 扩窗后 ~5 个月, 2026-09-12 重跑)",
       "d1_ready": n_ready, "m60_confirmed": n_conf,
       "armA_d1_only": sA, "armB_mtf_confirmed": sB, "delta_avg_pp": delta,
       "acceptance_n": ("UNKNOWN(<30)" if (sB.get("n") or 0) < 30 else
                        "PRELIMINARY(30-100)" if (sB.get("n") or 0) < 100 else
                        "VALIDATION(100-200)" if (sB.get("n") or 0) < 200 else "STRONG(≥200)"),
       "verdict": verdict, "runtime_s": round(time.time() - t0)}
print(f"D1 READY: {n_ready}  60m 确认: {n_conf}")
print(f"臂A(D1-only): {sA}")
print(f"臂B(D1+60m确认): {sB}")
print(f"Δ = {delta}pp → {verdict}")
json.dump(out, open(r"E:\test\smc_project\research\handover\F7_MultiTF事件链.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("已写 handover/F7_MultiTF事件链.json")
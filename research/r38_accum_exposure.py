# -*- coding: utf-8 -*-
"""r38_accum_exposure.py —— 用 R38ah 新规则复核 ACCUM×2 候选(敞口归一).

背景: R38l 报告 ACCUM×2 温和正面(PF 3.21→3.29, 累计 +5766→+6913) 并列为接线候选。
但 R38ah 沉淀的规则 R6 要求: **仓位/加权类改动必须做敞口归一** ——
因为累计收益只反映杠杆水平, 不反映 edge。

本脚本对 ACCUM×2 做严格复核:
  ① 复现 R38l 的原始数字(确认口径一致)
  ② 敞口归一后的"每单位敞口收益"对比
  ③ 与 R38ah 的 rank 加权结论对照(是否同型)

数据: combo_v20f_trades.csv EVENT 腿 + stage(从 r38_stage_rescan.json 取,
或现场重算 —— 本脚本现场重算以保证口径透明)。

判据(预注册): 若 ACCUM×2 的每单位敞口收益 **不高于**等权, 则其优势纯属杠杆,
应降级(与 rank 加权同型)。
纯研究, 不修改生产。
"""
import csv
import io
import json
import os
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
IS_END = "20250630"


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


code2file = {fn.split("_")[0]: os.path.join(KT, fn) for fn in os.listdir(KT)
             if fn.endswith("_daily_800.json")}
bar_cache = {}


def bars_of(code):
    if code not in bar_cache:
        p = code2file.get(code)
        if not p:
            bar_cache[code] = []
            return bar_cache[code]
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]),
                           "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def stage_of(bs, i):
    """与 gen_v20f2_wilder_h12 完全一致(仅 ret60 + 量比, 不含 ADX)。"""
    if i < 91:
        return None
    w60 = bs[i - 60:i]
    if len(w60) < 2:
        return None
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in bs[i - 20:i]) / 20
    v60 = sum(b["v"] for b in bs[i - 60:i]) / 60
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    return "UPTREND" if ret60 > 0 else "DOWNTREND"


rows = list(csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"),
                               encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
print("=" * 96)
print("ACCUM×2 候选的敞口归一复核 (EVENT n=%d)" % len(ev))
print("=" * 96)

recs = []
n_stage = 0
for r in ev:
    sym = str(r.get("symbol") or "").split(".")[0]
    d8 = str(r.get("entry_date") or "").replace("-", "")
    bs = bars_of(sym)
    st = None
    if bs:
        dates = [b["t"] for b in bs]
        if d8 in dates:
            ei = dates.index(d8)
            if ei - 1 >= 0:
                st = stage_of(bs, ei - 1)
    if st:
        n_stage += 1
    recs.append({"net": f(r["net_pnl_pct"]), "stage": st or "(未算出)", "d": d8})
print("stage 命中: %d / %d (%.1f%%)" % (n_stage, len(recs), 100 * n_stage / len(recs)))


def metrics(ws):
    """ws = [(net, weight)]"""
    c = [n * w for n, w in ws]
    tw = sum(w for _, w in ws)
    wins = [x for x in c if x > 0]
    loss = [x for x in c if x <= 0]
    pf = sum(wins) / abs(sum(loss)) if sum(loss) else 99.0
    eq = 0.0
    peak = 0.0
    mdd = 0.0
    for x in c:
        eq += x
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return {"n": len(c), "exp": round(tw, 0),
            "avg_exp": round(sum(c) / tw, 3) if tw else 0,
            "pf": round(pf, 2), "mdd": round(mdd, 0), "sum": round(sum(c), 0)}


def scheme(kind, rows_):
    if kind == "equal":
        return [(t["net"], 1.0) for t in rows_]
    if kind == "accum2":
        return [(t["net"], 2.0 if t["stage"] == "ACCUM" else 1.0) for t in rows_]


print("\n" + "=" * 96)
print("全样本对比 (含敞口列)")
print("=" * 96)
print("%-22s %7s %10s %8s %8s %10s" % ("方案", "敞口", "每单位%", "PF", "MDD%", "累计%"))
res = {}
for lab, kind in (("等权(现状)", "equal"), ("ACCUM×2", "accum2")):
    m = metrics(scheme(kind, recs))
    res[lab] = m
    print("%-22s %7.0f %+9.3f%% %8.2f %8.0f %+10.0f"
          % (lab, m["exp"], m["avg_exp"], m["pf"], m["mdd"], m["sum"]))

a, b = res["等权(现状)"], res["ACCUM×2"]
print("\n  Δ 每单位敞口收益: %+.3fpp" % (b["avg_exp"] - a["avg_exp"]))
print("  Δ PF: %+.2f" % (b["pf"] - a["pf"]))
print("  Δ MDD: %+.0f" % (b["mdd"] - a["mdd"]))
print("  敞口放大: %.2fx" % (b["exp"] / a["exp"] if a["exp"] else 0))

print("\n" + "=" * 96)
print("IS/OOS 双段(归一后)")
print("=" * 96)
print("%-22s %24s %24s" % ("方案", "IS (每单位%/PF)", "OOS (每单位%/PF)"))
for lab, kind in (("等权(现状)", "equal"), ("ACCUM×2", "accum2")):
    isr = [t for t in recs if t["d"] <= IS_END]
    oosr = [t for t in recs if t["d"] > IS_END]
    si = metrics(scheme(kind, isr))
    so = metrics(scheme(kind, oosr))
    print("%-22s %23s %23s"
          % (lab, "%+.3f%%/%.2f" % (si["avg_exp"], si["pf"]),
             "%+.3f%%/%.2f" % (so["avg_exp"], so["pf"])))

print("\n" + "=" * 96)
print("裁定 (预注册: ACCUM×2 需每单位敞口收益 > 等权 才算真实改进)")
print("=" * 96)
ok_exp = b["avg_exp"] > a["avg_exp"]
ok_pf = b["pf"] > a["pf"]
print("  每单位敞口收益 提升: %s (%+.3fpp)" % (ok_exp, b["avg_exp"] - a["avg_exp"]))
print("  PF 提升: %s (%+.2f)" % (ok_pf, b["pf"] - a["pf"]))
if ok_exp and ok_pf:
    print("\n  → ✅ ACCUM×2 **通过敞口归一检验**: 每单位收益与 PF 双双提升,")
    print("     优势**不是**纯杠杆 —— 与 rank 加权(R38ah 证伪)不同。")
    print("     代价: MDD 恶化 %+.0f, 敞口 +%.0f%%。" % (b["mdd"] - a["mdd"],
                                                   100 * (b["exp"] / a["exp"] - 1)))
else:
    print("\n  → ❌ ACCUM×2 未通过敞口归一检验 —— 其表面优势来自杠杆,")
    print("     与 R38ah rank 加权同型, 应降级。")
print("\n  ★ 对照 R38ah 结论: rank 加权归一后 **劣于** 硬门槛(纯杠杆);")
print("     本脚本将判定 ACCUM×2 是否属于同类。")
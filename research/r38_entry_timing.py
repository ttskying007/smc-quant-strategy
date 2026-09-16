# -*- coding: utf-8 -*-
"""r38_entry_timing.py —— 入场前短期动量能否区分"快速止损"与正常交易.

动机: R38an 出场诊断发现"持仓<2根K线者 100% 止损(n=120 全错)" -> 说明**入场后
快速下跌**是亏损主因, 指向**入场时机**问题。R38an 结论"剩余空间在入场择时质量"。

此前从未检验过**入场前短期动量**这一维度(特征集一直用 60 日/阶段/量比/ADX)。
本脚本补上: signal 日前 1/3/5 日动量 + signal 日涨跌, 看能否区分结果。

检验:
  ① 短动量 vs 快速止损率(hold_bars<3 且 reason=SL)
  ② 短动量分桶 vs 结果(avg/PF/wr)
  ③ 逐年/IS/OOS
  ④ 结合 ret60(超跌深度)是否叠加

判据(预注册): 短动量单调预测结果 + IS/OOS 双段一致 => 候选; 否则关闭。
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


rows = list(csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"),
                               encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]

recs = []
n_hit = 0
for r in ev:
    sym = str(r["symbol"]).split(".")[0]
    d8 = str(r["entry_date"]).replace("-", "")
    bs = bars_of(sym)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if d8 not in dates:
        continue
    ei = dates.index(d8)
    i = ei - 1  # signal 日
    if i < 8:
        continue
    c = bs[i]["c"]
    r1 = c / bs[i - 1]["c"] - 1 if bs[i - 1]["c"] else 0
    r3 = c / bs[i - 3]["c"] - 1 if bs[i - 3]["c"] else 0
    r5 = c / bs[i - 5]["c"] - 1 if bs[i - 5]["c"] else 0
    r20 = c / bs[i - 20]["c"] - 1 if i >= 20 and bs[i - 20]["c"] else 0
    # 快速止损: 持仓<3 且 reason=SL
    fast_sl = int(f(r.get("hold_bars")) < 3 and (r.get("reason") or "").startswith("SL"))
    recs.append({"net": f(r["net_pnl_pct"]), "d": d8, "r1": r1, "r3": r3,
                 "r5": r5, "r20": r20, "fast_sl": fast_sl,
                 "hold": f(r.get("hold_bars")), "reason": r.get("reason") or ""})
    n_hit += 1

print("=" * 100)
print("入场前短期动量检验 (可算 %d / %d)" % (n_hit, len(ev)))
print("=" * 100)


def stats(rs, key="net"):
    if not rs:
        return None
    p = [r[key] for r in rs]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    return {"n": len(p), "avg": round(sum(p) / len(p), 2),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2)}


def bucket(key, bins, labels):
    print("\n  %s:" % key)
    print("  %-14s %6s %9s %8s %9s %8s" % ("区间", "n", "avg%", "wr", "PF", "快止损%"))
    for (lo, hi), lab in zip(bins, labels):
        sub = [r for r in recs if lo <= r[key] < hi]
        s = stats(sub)
        if not s:
            continue
        fs = 100 * sum(1 for r in sub if r["fast_sl"]) / s["n"]
        print("  %-14s %6d %+8.2f%% %7.1f%% %9.2f %7.1f%%" % (lab, s["n"], s["avg"], s["wr"], s["pf"], fs))


print("\n" + "=" * 100)
print("① signal 日 1 日动量(r1)")
print("=" * 100)
bucket("r1", [(-99, -0.05), (-0.05, 0), (0, 0.02), (0.02, 0.05), (0.05, 0.08), (0.08, 99)],
       ["<-5%", "[-5,0)", "[0,2%)", "[2,5%)", "[5,8%)", ">=8%"])

print("\n" + "=" * 100)
print("② 3 日动量(r3)")
print("=" * 100)
bucket("r3", [(-99, -0.08), (-0.08, -0.03), (-0.03, 0), (0, 0.05), (0.05, 0.10), (0.10, 99)],
       ["<-8%", "[-8,-3)", "[-3,0)", "[0,5%)", "[5,10%)", ">=10%"])

print("\n" + "=" * 100)
print("③ 5 日动量(r5)")
print("=" * 100)
bucket("r5", [(-99, -0.10), (-0.10, -0.05), (-0.05, 0), (0, 0.05), (0.05, 0.12), (0.12, 99)],
       ["<-10%", "[-10,-5)", "[-5,0)", "[0,5%)", "[5,12%)", ">=12%"])

print("\n" + "=" * 100)
print("④ 5日动量 IS/OOS 双段(看是否跨期稳定)")
print("=" * 100)
print("  %-18s %24s %24s" % ("r5 组", "IS (n/avg/PF)", "OOS (n/avg/PF)"))
for lo, hi, lab in [(-99, -0.05, "r5<-5%"), (-0.05, 0, "-5~0"), (0, 0.05, "0~5"), (0.05, 99, "r5>=5%")]:
    isr = [r for r in recs if lo <= r["r5"] < hi and r["d"] <= IS_END]
    oosr = [r for r in recs if lo <= r["r5"] < hi and r["d"] > IS_END]
    si, so = stats(isr), stats(oosr)
    ci = "%d %+.2f%%/%.2f" % (si["n"], si["avg"], si["pf"]) if si else "—"
    co = "%d %+.2f%%/%.2f" % (so["n"], so["avg"], so["pf"]) if so else "—"
    print("  %-18s %24s %24s" % (lab, ci, co))

print("\n" + "=" * 100)
print("⑤ r20 与 r5 交互(中期动量 × 短期动量)")
print("=" * 100)
print("  %-26s %20s %20s" % ("r20 × r5", "快止损%", "avg%"))
for rl, rh, rlab in [(-99, -0.25, "r20<-25%"), (-0.25, -0.15, "-25~-15"), (-0.15, 0, "r20>-15")]:
    for ml, mh, mlab in [(-99, 0, "r5<0"), (0, 99, "r5>=0")]:
        sub = [r for r in recs if rl <= r["r20"] < rh and ml <= r["r5"] < mh]
        if not sub:
            continue
        s = stats(sub)
        fs = 100 * sum(1 for r in sub if r["fast_sl"]) / s["n"]
        print("  %-26s %18.1f%% %+19.2f%%" % ("%s × %s" % (rlab, mlab), fs, s["avg"]))

print("\n" + "=" * 100)
print("裁定")
print("=" * 100)
print("  若短动量单调预测结果且 IS/OOS 一致 => 入场择时候选")
print("  若否 => 现有入场(披露日×0.99回踩)已达局部最优, 关闭")
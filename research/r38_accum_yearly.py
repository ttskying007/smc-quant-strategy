# -*- coding: utf-8 -*-
"""r38_accum_yearly.py —— ACCUM×2 逐年分解(定位 IS劣化/OOS改善 的来源).

r38_accum_exposure.py 结果:
  全样本: 等权 每单位+3.767%/PF3.63 | ACCUM×2 **+3.907%/PF3.74** (✅ 通过归一)
  但分段: IS  等权 3.626/3.52 → ACCUM×2 3.563/3.45 (**劣化**)
          OOS 等权 4.266/4.03 → ACCUM×2 **4.986/4.75** (大幅改善)
→ 改善**全部集中在 OOS**, 这是需要警惕的模式(参照 R38h 单年假象)。

本脚本逐年分解, 判定:
  · 若改善集中在单一年份(如 2026) → 与 R38h 同型, 属时段特异性
  · 若跨多年稳定 → 才是真实改进
判据(预注册): 需 **≥2 个年份** 同时满足 (每单位收益提升 且 PF 提升)。
纯研究。
"""
import csv
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
YEARS = ("2023", "2024", "2025", "2026")


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

recs = []
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
    recs.append({"net": f(r["net_pnl_pct"]), "stage": st or "?", "d": d8})


def metrics(ws):
    c = [n * w for n, w in ws]
    tw = sum(w for _, w in ws)
    wins = [x for x in c if x > 0]
    loss = [x for x in c if x <= 0]
    pf = sum(wins) / abs(sum(loss)) if sum(loss) else 99.0
    return {"n": len(c), "exp": round(tw, 0),
            "avg_exp": round(sum(c) / tw, 3) if tw else 0,
            "pf": round(pf, 2), "sum": round(sum(c), 0)}


print("=" * 100)
print("ACCUM×2 逐年分解 (敞口归一后)")
print("=" * 100)
print("%-8s %30s %30s %8s" % ("年", "等权(每单位%/PF)", "ACCUM×2(每单位%/PF)", "裁定"))
improved = []
for y in YEARS:
    rs = [t for t in recs if t["d"][:4] == y]
    if not rs:
        continue
    a = metrics([(t["net"], 1.0) for t in rs])
    b = metrics([(t["net"], 2.0 if t["stage"] == "ACCUM" else 1.0) for t in rs])
    ok = b["avg_exp"] > a["avg_exp"] and b["pf"] > a["pf"]
    if ok:
        improved.append(y)
    n_acc = sum(1 for t in rs if t["stage"] == "ACCUM")
    print("%-8s %29s %29s %8s"
          % (y, "%+.3f%%/%.2f" % (a["avg_exp"], a["pf"]),
             "%+.3f%%/%.2f" % (b["avg_exp"], b["pf"]),
             "改善" if ok else "**劣化**"))
    print("%-8s   (ACCUM n=%d / 总 n=%d)" % ("", n_acc, len(rs)))

print("\n" + "=" * 100)
print("ACCUM 子集本身的逐年质量(为何 IS 劣化而 OOS 改善?)")
print("=" * 100)
print("%-8s %26s %26s" % ("年", "ACCUM 子集(avg/PF)", "非ACCUM(avg/PF)"))
for y in YEARS:
    rs = [t for t in recs if t["d"][:4] == y]
    acc = [t for t in rs if t["stage"] == "ACCUM"]
    oth = [t for t in rs if t["stage"] != "ACCUM"]
    def s(ts):
        if not ts:
            return "—"
        p = [t["net"] for t in ts]
        w = [x for x in p if x > 0]
        l = [x for x in p if x <= 0]
        pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
        return "n=%d %+.2f%%/%.2f" % (len(p), sum(p) / len(p), pf)
    print("%-8s %26s %26s" % (y, s(acc), s(oth)))

print("\n" + "=" * 100)
print("裁定 (预注册: 需 >=2 个年份同时 每单位收益与PF 双升)")
print("=" * 100)
print("  改善年份: %s (%d 个)" % (", ".join(improved) or "无", len(improved)))
if len(improved) >= 2:
    print("\n  → ✅ ACCUM×2 跨多年改善(%d年) —— 真实改进, 非单年假象" % len(improved))
    print("     但仍需注意: 全样本优势主要来自 OOS 段(见 r38_accum_exposure)")
else:
    print("\n  → ❌ 改善仅集中在 %s —— 与 R38h(技术腿单年假象) 同型" % (", ".join(improved) or "无"))
    print("     IS 劣化 + OOS 改善 的模式说明: 优势来自特定时段, 不稳健")
print("\n  对照: R38ah rank 加权(归一后劣于硬门槛=纯杠杆);")
print("        本候选(归一后通过但集中于OOS) —— 属**第三种情形**: 有非杠杆价值但不稳健。")
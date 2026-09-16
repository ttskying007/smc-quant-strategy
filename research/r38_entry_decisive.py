# -*- coding: utf-8 -*-
"""r38_entry_decisive.py —— 入场择时交互的决定性 IS/OOS 分解.

r38_entry_timing 发现:
  ① 5日动量简单过滤 IS/OOS **方向相反**(IS 强势最优 +5.33%/PF7.24;
     OOS 弱势最优 +12.95%/PF23.30, n=43) -> 疑为 2024 单事件
  ② 交互「深度超跌(r20<-25%) × 短期企稳(r5>=0)」是唯一低风险组合
     (快止损 0%, avg+10.96%) —— 但 r20<-25% 的票可能几乎全在 2024-02

决定性检验(预注册):
  ① r5 简单过滤的逐年 + IS/OOS -> 确认是否 2024 驱动
  ② r20×r5 交互的逐年 + IS/OOS + 2024-02 剔除
判据: 若交互优势在剔除 2024-02 后消失 -> 单一事件, 否决
      若逐年跨期稳定 -> 真实入场择时信号
纯研究。
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
    i = ei - 1
    if i < 20:
        continue
    c = bs[i]["c"]
    r5 = c / bs[i - 5]["c"] - 1 if bs[i - 5]["c"] else 0
    r20 = c / bs[i - 20]["c"] - 1 if bs[i - 20]["c"] else 0
    recs.append({"net": f(r["net_pnl_pct"]), "d": d8, "r5": r5, "r20": r20})

print("=" * 96)
print("入场择时交互决定性分解 (n=%d)" % len(recs))
print("=" * 96)


def stats(rs):
    if not rs:
        return None
    p = [r["net"] for r in rs]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    return {"n": len(p), "avg": round(sum(p) / len(p), 2),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2)}


print("\n① r5 简单过滤逐年(确认 2024 驱动)")
print("  %-14s %20s %20s" % ("r5 组", "IS (n/avg/PF)", "OOS (n/avg/PF)"))
for lo, hi, lab in [(-99, 0, "r5<0(弱势)"), (0, 99, "r5>=0(强势)")]:
    isr = [r for r in recs if lo <= r["r5"] < hi and r["d"] <= IS_END]
    oosr = [r for r in recs if lo <= r["r5"] < hi and r["d"] > IS_END]
    si, so = stats(isr), stats(oosr)
    print("  %-14s %20s %20s"
          % (lab, "%d %+.2f%%/%.2f" % (si["n"], si["avg"], si["pf"]),
             "%d %+.2f%%/%.2f" % (so["n"], so["avg"], so["pf"])))

print("\n  逐年(r5<0 vs r5>=0):")
for y in ("2023", "2024", "2025", "2026"):
    a = stats([r for r in recs if r["d"][:4] == y and r["r5"] < 0])
    b = stats([r for r in recs if r["d"][:4] == y and r["r5"] >= 0])
    ca = "%d %+.2f%%/%.2f" % (a["n"], a["avg"], a["pf"]) if a else "—"
    cb = "%d %+.2f%%/%.2f" % (b["n"], b["avg"], b["pf"]) if b else "—"
    print("  %s: 弱势(r5<0) %-22s | 强势(r5>=0) %-22s" % (y, ca, cb))

print("\n" + "=" * 96)
print("② 交互「深度超跌(r20<-25%)×短期企稳(r5>=0)」")
print("=" * 96)
deep = [r for r in recs if r["r20"] < -0.25]
calm = [r for r in deep if r["r5"] >= 0]
panic = [r for r in deep if r["r5"] < 0]
print("  深度超跌(r20 < -25%%) n=%d" % len(deep))
for lab, grp in (("  ×企稳(r5>=0)", calm), ("  ×弱势(r5<0)", panic)):
    s = stats(grp)
    if s:
        byy = defaultdict(list)
        for r in grp:
            byy[r["d"][:4]].append(r)
        ystr = " | ".join("%s:%d(%+.1f%%)" % (y, len(v), sum(r["net"] for r in v) / len(v))
                          for y, v in sorted(byy.items()))
        print("%s n=%d avg=%+.2f%% PF=%.2f | 逐年 %s" % (lab, s["n"], s["avg"], s["pf"], ystr))

print("\n  IS/OOS:")
for lab, grp in (("×企稳(r5>=0)", calm), ("×弱势(r5<0)", panic)):
    isr = [r for r in grp if r["d"] <= IS_END]
    oosr = [r for r in grp if r["d"] > IS_END]
    si, so = stats(isr), stats(oosr)
    print("  %s: IS %s | OOS %s"
          % (lab, "%d %+.2f%%/%.2f" % (si["n"], si["avg"], si["pf"]) if si else "—",
             "%d %+.2f%%/%.2f" % (so["n"], so["avg"], so["pf"]) if so else "—"))

print("\n  剔除 2024-02 后:")
no_feb = [r for r in calm if not r["d"].startswith("2024-02")]
s = stats(no_feb)
print("  ×企稳 剔除2024-02: n=%d avg=%+.2f%% PF=%.2f" % (s["n"], s["avg"], s["pf"]))
if no_feb:
    byy = defaultdict(list)
    for r in no_feb:
        byy[r["d"][:4]].append(r)
    print("  逐年: %s" % " | ".join("%s:%d(%+.1f%%)" % (y, len(v), sum(r["net"] for r in v) / len(v))
                                   for y, v in sorted(byy.items())))

print("\n" + "=" * 96)
print("裁定")
print("=" * 96)
print("  若交互优势在剔除 2024-02 后消失 -> 单一事件, 否决")
print("  若逐年跨期稳定 -> 真实入场择时信号, 全链路复核")
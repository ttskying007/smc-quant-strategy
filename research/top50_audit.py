# -*- coding: utf-8 -*-
"""Top50% 精选方案集中度审计（防止精选后单年/单月依赖）"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
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
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def score_trade(t):
    code = str(t.get("symbol", "")).split(".")[0]
    ed = str(t.get("entry_date", ""))
    bs = bars_of(code)
    if not bs:
        return 0.0
    dates = [b["t"] for b in bs]
    if ed not in dates:
        prev = [d for d in dates if d < ed]
        if not prev:
            return 0.0
        i = dates.index(prev[-1])
    else:
        i = dates.index(ed)
    if i < 90:
        return 0.0
    src = t.get("src", "")
    if src == "EVENT":
        w90 = bs[i - 90:i]
        w20 = bs[i - 20:i]
        ret90 = w90[-1]["c"] / w90[0]["c"] - 1
        v20 = sum(b["v"] for b in w20) / 20
        v90 = sum(b["v"] for b in w90) / 90
        deep = ret90 < -0.20 and (v20 / v90 if v90 else 1) < 0.75
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20
        return (2 if deep else 0) + (1 if vol20 > 0.041 else 0)
    if src == "CONT":
        w20 = bs[i - 20:i]
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20
        return 1 if vol20 < 0.041 else 0
    fvg_cnt = sum(1 for k in range(max(3, i - 12), i) if bs[k]["h"] < bs[k - 2]["l"])
    return fvg_cnt


scored = sorted([(t, score_trade(t)) for t in trades], key=lambda x: x[1], reverse=True)
top50 = [t for t, s in scored[:len(scored) // 2]]
print("Top50% 精选:", len(top50))

# yearly + monthly concentration
by_y = defaultdict(list)
for t in top50:
    by_y[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
print("\n=== 逐年 ===")
for y in ("2024", "2025", "2026"):
    rs = by_y.get(y, [])
    if rs:
        w = sum(1 for x in rs if x > 0)
        print(f"  {y}: n={len(rs)} ({100*len(rs)/len(top50):.0f}%) WR={100*w/len(rs):.0f}% avg={sum(rs)/len(rs):+.2f}%")

print("\n=== 2025 月度（精选，检查均衡）===")
by_m = defaultdict(list)
for t in top50:
    if str(t["entry_date"]).startswith("2025"):
        by_m[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
for m in sorted(by_m):
    rs = by_m[m]
    print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")

print("\n=== 2026 月度（精选）===")
by_m26 = defaultdict(list)
for t in top50:
    if str(t["entry_date"]).startswith("2026"):
        by_m26[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
for m in sorted(by_m26):
    rs = by_m26[m]
    print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")

# stock concentration
from collections import Counter
codes = Counter(str(t.get("symbol", "")).split(".")[0] for t in top50)
top_stocks = codes.most_common(5)
print(f"\n=== 股票集中度（前5）===")
for c, n in top_stocks:
    print(f"  {c}: {n} 笔 ({100*n/len(top50):.1f}%)")

# -*- coding: utf-8 -*-
"""v20c 超额收益分析：组合 vs 市场基准（每年超额 = 策略真实价值）"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

# benchmark: 000001 (平安银行, 大盘蓝筹代理) yearly 15d forward returns
def bars(path):
    raw = json.load(open(path, encoding="utf-8"))
    bs = []
    for r in raw:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("c"):
            bs.append({"t": t, "o": float(r["o"]), "c": float(r["c"])})
    bs.sort(key=lambda b: b["t"])
    return bs

bench = bars(os.path.join(KT, "000001_SZ_daily_800.json"))
bench_by_ym = defaultdict(list)
if bench:
    for i in range(len(bench) - 15):
        m = bench[i]["t"][:6]
        if bench[i]["o"] > 0:
            bench_by_ym[m].append((bench[i + 15]["c"] / bench[i]["o"] - 1) * 100)

# combo yearly avg + benchmark yearly avg (avg of monthly means)
combo_by_y = defaultdict(list)
for t in trades:
    combo_by_y[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])

print("=== v20c 组合 vs 市场基准（000001 15日）===")
for y in ("2024", "2025", "2026"):
    crs = combo_by_y.get(y, [])
    # benchmark for that year: avg of all 15d windows in that year
    brs = []
    for m, v in bench_by_ym.items():
        if m.startswith(y):
            brs += v
    if crs and brs:
        ca = sum(crs) / len(crs)
        ba = sum(brs) / len(brs)
        print(f"  {y}: 组合 {ca:+.2f}% vs 基准 {ba:+.2f}% = 超额 {ca-ba:+.2f}%")

# overall
crs = [t["net_pnl_pct"] for t in trades]
brs_all = []
for m, v in bench_by_ym.items():
    if m >= "202309":
        brs_all += v
ca = sum(crs) / len(crs)
ba = sum(brs_all) / len(brs_all) if brs_all else 0
print(f"\n总体: 组合 {ca:+.2f}% vs 基准 {ba:+.2f}% = 超额 {ca-ba:+.2f}%")

# -*- coding: utf-8 -*-
"""市场 regime 细分：组合在不同市场状态（MA20 上行/下行）的表现
普适性最终验证（用户"普适性，不能有偏概率"）"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

# market regime proxy: 000001 (平安银行) MA20 slope on entry date
raw = json.load(open(os.path.join(KT, "000001_SZ_daily_800.json"), encoding="utf-8"))
bench = []
for r in raw:
    t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
    if t and r.get("c"):
        bench.append({"t": t, "c": float(r["c"])})
bench.sort(key=lambda b: b["t"])

regime_map = {}
for i in range(20, len(bench)):
    ma20 = sum(bench[k]["c"] for k in range(i - 19, i + 1)) / 20
    ma20_prev = sum(bench[k]["c"] for k in range(i - 20, i)) / 20
    regime_map[bench[i]["t"]] = "UP" if ma20 > ma20_prev else "DOWN"

up = [t for t in trades if regime_map.get(str(t["entry_date"])) == "UP"]
down = [t for t in trades if regime_map.get(str(t["entry_date"])) == "DOWN"]
print(f"总 {len(trades)} | UP regime {len(up)} | DOWN regime {len(down)}")


def report(label, rs):
    if len(rs) < 300:
        print(f"{label}: n={len(rs)} (过小)")
        return
    for t in rs:
        t["t1_violation"] = "False"
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    line = f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']}"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%"
    print(line)


print("\n=== 市场 regime 细分 ===")
report("市场上行（MA20↑）", up)
report("市场下行（MA20↓）", down)

# -*- coding: utf-8 -*-
"""修复后深度审计：v20f Bootstrap + 模拟状态 + 剩余问题"""
import csv, io, json, random, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

print("=== 1. v20f 全量 Bootstrap（修复后）===")
trades = []
with open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)
pnls = [t["net_pnl_pct"] for t in trades]
n = len(pnls)
random.seed(42)
avgs = []
for _ in range(1000):
    sub = random.sample(pnls, int(n * 0.6))
    avgs.append(sum(sub) / len(sub))
avgs.sort()
print(f"v20f: {n} 笔, avg {sum(pnls)/n:+.2f}%")
print(f"Bootstrap: 中位 {avgs[500]:+.2f}% | P5 {avgs[50]:+.2f}% | P95 {avgs[950]:+.2f}% | 正 {sum(1 for a in avgs if a>0)}/1000")

print("\n=== 2. 模拟持仓（修复后）===")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
print(f"ledger: {dict(Counter(t.get('status') for t in led))}")
active = [t for t in led if t.get("status") != "CLOSED"]
mp = [t.get("mark_pnl_pct") for t in active if t.get("mark_pnl_pct") is not None]
if mp:
    print(f"活跃浮盈: avg {sum(mp)/len(mp):+.2f}% (n={len(mp)})")
# rank coverage
rk = sum(1 for t in led if t.get("rank_score") is not None)
print(f"rank_score 覆盖: {rk}/{len(led)} ({100*rk/len(led):.0f}%)")
# tiered hits
tp1 = sum(1 for t in active if t.get("tp1_hit"))
print(f"TP1 触发: {tp1} | SL距离>8%降仓: {sum(1 for t in active if t.get('position_scale'))}")

print("\n=== 3. 剩余问题扫描 ===")
# 延续腿样本
cont = [t for t in trades if t.get("src") == "CONT"]
print(f"延续腿: {len(cont)} 笔 (样本少)")
# 皇冠集中
ev = [t for t in trades if t.get("src") == "EVENT"]
crown = [t for t in ev if int(t.get("rank", 0)) >= 6]
if crown:
    y24 = sum(1 for t in crown if str(t["entry_date"])[:4] == "2024")
    print(f"皇冠: {len(crown)} 笔, 2024 占 {100*y24/len(crown):.0f}% (集中)")

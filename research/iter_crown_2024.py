# -*- coding: utf-8 -*-
"""皇冠 2024 集中根因：特征分布（放量/连续放量/跨度）vs 年度
判断皇冠集中是特征问题（2024 更多强信号）还是市场问题"""
import csv, io, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 从 nolookahead rank 数据重建特征分布（用 v20f CSV + 特征从 CSV 不可得，重建近似）
# 用 iter_nolookahead_rank.py 的事件数据（含 rank）—— 简化：用 v20f CSV rank 列
trades = []
with open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        trades.append(r)

ev = [t for t in trades if t.get("src") == "EVENT"]
print(f"事件: {len(ev)}\n")

# rank 分布 by year
print("=== rank 分布 by 年度（事件）===")
for y in ("2024", "2025", "2026"):
    ys = [t for t in ev if str(t["entry_date"])[:4] == y]
    rk_dist = defaultdict(int)
    for t in ys:
        rk_dist[int(t.get("rank", 0))] += 1
    total = len(ys)
    print(f"  {y}: n={total}")
    for rk in sorted(rk_dist):
        print(f"    rank={rk}: {rk_dist[rk]} ({100*rk_dist[rk]/total:.0f}%)")

# 皇冠占比 by year
print("\n=== 皇冠(rank≥6)占比 by 年度 ===")
for y in ("2024", "2025", "2026"):
    ys = [t for t in ev if str(t["entry_date"])[:4] == y]
    crown = [t for t in ys if int(t.get("rank", 0)) >= 6]
    print(f"  {y}: 皇冠 {len(crown)}/{len(ys)} ({100*len(crown)/len(ys):.1f}%)")

# 检查: 2024 是否是反弹市（皇冠条件易满足）
# 皇冠 rank≥6 需要 6 项特征，检查 2024 vs 2025 特征达标率差异（用 rank>=4 占比近似）
print("\n=== 特征强度（rank≥4 占比）by 年度 ===")
for y in ("2024", "2025", "2026"):
    ys = [t for t in ev if str(t["entry_date"])[:4] == y]
    strong = [t for t in ys if int(t.get("rank", 0)) >= 4]
    print(f"  {y}: rank≥4 {len(strong)}/{len(ys)} ({100*len(strong)/len(ys):.1f}%)")

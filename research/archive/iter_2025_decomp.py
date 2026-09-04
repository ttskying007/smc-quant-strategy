# -*- coding: utf-8 -*-
"""2025 弱市拆解：事件腿 2025 +3.34% 弱 —— 按子集（类型/阶段/rank）找拖累源"""
import csv, io, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

ev = [t for t in trades if t.get("src") == "EVENT"]
print(f"事件: {len(ev)} 笔\n")

def stats(rs):
    if not rs:
        return None
    pnls = [t["net_pnl_pct"] for t in rs]
    wins = [x for x in pnls if x > 0]
    pf = sum(wins) / abs(sum(x for x in pnls if x <= 0)) if any(x <= 0 for x in pnls) else 99
    return len(pnls), sum(pnls) / len(pnls), 100 * len(wins) / len(pnls), pf

print("=== 2025 vs 2024/2026 对比 ===")
for y in ("2024", "2025", "2026"):
    ys = [t for t in ev if str(t["entry_date"])[:4] == y]
    s = stats(ys)
    print(f"  {y}: n={s[0]} avg={s[1]:+.2f}% WR={s[2]:.0f}% PF={s[3]:.2f}")

print("\n=== 2025 按 rank 分组 ===")
for rk in (2, 3, 4, 5):
    rs = [t for t in ev if str(t["entry_date"])[:4] == "2025" and int(t.get("rank", 0)) == rk]
    s = stats(rs)
    if s:
        print(f"  rank={rk}: n={s[0]} avg={s[1]:+.2f}% WR={s[2]:.0f}% PF={s[3]:.2f}")

print("\n=== 2025 皇冠 vs 非皇冠 ===")
crown25 = [t for t in ev if str(t["entry_date"])[:4] == "2025" and int(t.get("rank", 0)) >= 6]
non25 = [t for t in ev if str(t["entry_date"])[:4] == "2025" and int(t.get("rank", 0)) < 6]
for label, rs in (("皇冠(rank≥6)", crown25), ("非皇冠(rank<6)", non25)):
    s = stats(rs)
    if s:
        print(f"  {label}: n={s[0]} avg={s[1]:+.2f}% WR={s[2]:.0f}% PF={s[3]:.2f}")

print("\n=== 2025 月度分布 ===")
by_m = defaultdict(list)
for t in ev:
    if str(t["entry_date"])[:4] == "2025":
        by_m[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
for m in sorted(by_m):
    rs = by_m[m]
    print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")

# -*- coding: utf-8 -*-
"""资金分层受控对比：修复后合同（v20f）的皇冠/rank≥4/全量收益
最终确认资金分层方案（<50万皇冠/50-700万rank≥4/700万+全量）"""
import csv, io, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

ev = [t for t in trades if t.get("src") == "EVENT"]
cont = [t for t in trades if t.get("src") == "CONT"]

def stats(rs):
    if not rs:
        return None
    pnls = [t["net_pnl_pct"] for t in rs]
    wins = [x for x in pnls if x > 0]
    pf = sum(wins) / abs(sum(x for x in pnls if x <= 0)) if any(x <= 0 for x in pnls) else 99
    return len(pnls), sum(pnls) / len(pnls), 100 * len(wins) / len(pnls), pf


def report(label, rs):
    s = stats(rs)
    if not s:
        print(f"{label}: 无")
        return
    line = f"{label}: n={s[0]} avg={s[1]:+.2f}% WR={s[2]:.0f}% PF={s[3]:.2f}"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"])[:4] == y]
        if ys:
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%({len(ys)})"
    print(line)


print("=== 资金分层受控对比（修复后 v20f）===\n")
# 事件腿分层
crown = [t for t in ev if int(t.get("rank", 0)) >= 6]
r5 = [t for t in ev if int(t.get("rank", 0)) >= 5]
r4 = [t for t in ev if int(t.get("rank", 0)) >= 4]
report("皇冠(rank≥6)", crown)
report("rank≥5", r5)
report("rank≥4", r4)
report("全部事件", ev)
report("延续腿", cont)
# 组合（事件+延续）
report("全量组合(事件+延续)", trades)

print("\n=== 分层年度信号供给 ===")
for label, rs in (("皇冠", crown), ("rank≥5", r5), ("rank≥4", r4)):
    by_y = defaultdict(int)
    for t in rs:
        by_y[str(t["entry_date"])[:4]] += 1
    print(f"  {label}: {dict(sorted(by_y.items()))}")

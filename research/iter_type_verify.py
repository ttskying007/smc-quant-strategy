# -*- coding: utf-8 -*-
"""事件类型实盘验证：首次/方案（新信息）vs 进展（旧信息）的模拟持仓浮盈对比"""
import io, json, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
active = [t for t in led if t.get("status") in ("OPEN", "FILLED") and t.get("mark_pnl_pct") is not None]

by_type = defaultdict(list)
for t in active:
    title = str(t.get("trigger", "")) + str(t.get("signal_combo", ""))
    sig = str(t.get("signal_date", ""))
    # classify by signal combo + title hints
    combo = str(t.get("signal_combo", ""))
    is_new = "方案" in title or "首次" in title or "计划" in title
    key = "首次/方案" if is_new else ("进展/其他" if "进展" in title else "普通")
    by_type[key].append(t["mark_pnl_pct"])

print("=== 事件类型持仓浮盈对比（当前）===")
for k, ps in sorted(by_type.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
    n = len(ps)
    wins = sum(1 for x in ps if x > 0)
    print(f"  {k}: n={n} avg={sum(ps)/n:+.2f}% 正={wins} 负={n-wins}")

# by signal_combo
print("\n=== 按信号组合 ===")
by_combo = defaultdict(list)
for t in active:
    by_combo[str(t.get("signal_combo", "?"))].append(t["mark_pnl_pct"])
for k, ps in sorted(by_combo.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
    print(f"  {k}: n={len(ps)} avg={sum(ps)/len(ps):+.2f}%")

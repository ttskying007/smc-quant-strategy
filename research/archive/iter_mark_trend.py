# -*- coding: utf-8 -*-
"""模拟持仓浮盈分析：当前活跃持仓（含过滤修复前/后）的表现分布"""
import io, json, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
active = [t for t in led if t.get("status") in ("OPEN", "FILLED")]
print(f"活跃持仓: {len(active)} 笔")

# with mark pnl
with_pnl = [t for t in active if t.get("mark_pnl_pct") is not None]
if with_pnl:
    pnls = [t["mark_pnl_pct"] for t in with_pnl]
    print(f"有浮盈: {len(with_pnl)} | 平均 {sum(pnls)/len(pnls):+.2f}% | 正 {sum(1 for x in pnls if x>0)} 负 {sum(1 for x in pnls if x<0)}")

# by signal date bucket (pre/post filter fix)
pre = [t for t in with_pnl if str(t.get("signal_date", "")) < "2026-08-17"]
post = [t for t in with_pnl if str(t.get("signal_date", "")) >= "2026-08-17"]
for label, rs in (("8/17前(过滤前选入)", pre), ("8/17起(公告修复后选入)", post)):
    if rs:
        p = [t["mark_pnl_pct"] for t in rs]
        print(f"  {label}: n={len(rs)} avg={sum(p)/len(p):+.2f}% 正={sum(1 for x in p if x>0)} 负={sum(1 for x in p if x<0)}")

# by stage
from collections import defaultdict
by_stage = defaultdict(list)
for t in with_pnl:
    by_stage[t.get("stage", t.get("signal_combo", "?"))].append(t["mark_pnl_pct"])
print("\n=== 按阶段/信号 ===")
for st, ps in sorted(by_stage.items(), key=lambda kv: -sum(kv[1])/len(kv[1])):
    print(f"  {st}: n={len(ps)} avg={sum(ps)/len(ps):+.2f}%")

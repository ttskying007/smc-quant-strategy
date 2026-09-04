# -*- coding: utf-8 -*-
"""分层 TP/SL 实盘触发率：活跃持仓的 TP1/TP2 触发 + CLOSED 出场分布
验证卖点设计（分层止盈实际工作）"""
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
active = [t for t in led if t.get("status") != "CLOSED"]
closed = [t for t in led if t.get("status") == "CLOSED"]

print(f"活跃 {len(active)} | CLOSED {len(closed)}\n")
print("=== 分层止盈触发率（活跃持仓）===")
tp1 = sum(1 for t in active if t.get("tp1_hit"))
tp2 = sum(1 for t in active if t.get("tp2_hit"))
print(f"TP1 触发: {tp1}/{len(active)} ({100*tp1/len(active):.1f}%)")
print(f"TP2 触发: {tp2}/{len(active)} ({100*tp2/len(active):.1f}%)")
print(f"TP1→TP2 链: {100*tp2/tp1:.0f}%（TP1 后继续到 TP2 的比例）" if tp1 else "无")

print("\n=== CLOSED 出场分布 ===")
print(dict(Counter(t.get("exit_reason") for t in closed)))
if closed:
    pnls = [t.get("pnl_pct", 0) for t in closed if t.get("pnl_pct") is not None]
    if pnls:
        wins = [x for x in pnls if x > 0]
        print(f"平均 {sum(pnls)/len(pnls):+.2f}% | 胜率 {100*len(wins)/len(pnls):.0f}% | PF {sum(wins)/abs(sum(x for x in pnls if x<=0)) if any(x<=0 for x in pnls) else 99:.2f}")

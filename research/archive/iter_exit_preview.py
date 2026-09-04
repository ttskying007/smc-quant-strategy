# -*- coding: utf-8 -*-
"""纸面平仓情景预评估：8-12/13/14 持仓（106 笔）在当前价位的潜在平仓结果
（为 9 月初裁决准备：统计分布 + 与回测预期对比）"""
import io, json, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
targets = [t for t in led if str(t.get("signal_date", "") or t.get("disclose_date", "")) in ("2026-08-12", "2026-08-13", "2026-08-14") and t.get("mark_pnl_pct") is not None]
pnls = [t["mark_pnl_pct"] for t in targets]
n = len(pnls)
if not n:
    print("无数据")
    sys.exit()
wins = [x for x in pnls if x > 0]
losses = [x for x in pnls if x <= 0]
print(f"8-12/13/14 持仓: {n} 笔（当前浮盈）")
print(f"平均浮盈: {sum(pnls)/n:+.2f}%")
print(f"胜率: {100*len(wins)/n:.0f}%（当前）")
print(f"盈利合计: {sum(wins):+.1f}% | 亏损合计: {sum(losses):+.1f}%")
print(f"盈亏比(当前): {(sum(wins)/len(wins))/(abs(sum(losses))/len(losses)) if losses and wins else 'N/A':.2f}" if False else f"PF(当前): {(sum(wins)/abs(sum(losses))) if losses else 99:.2f}")
# distribution
p05 = sorted(pnls)[int(n*0.05)]
p50 = sorted(pnls)[n//2]
p95 = sorted(pnls)[int(n*0.95)]
print(f"分布: P5={p05:+.1f}% P50={p50:+.1f}% P95={p95:+.1f}%")
# worst/best
print(f"最差: {min(pnls):+.2f}% | 最好: {max(pnls):+.2f}%")
# vs backtest expectation (event avg ~+6.5%)
print(f"\n对比: 回测事件 avg +6.5% vs 当前浮盈 {sum(pnls)/n:+.2f}%（8-20 弱市，持有期未结束）")
print("裁决标准: 9 月初 15 日持有到期，用当日收盘价平仓，与回测 avg 对比")

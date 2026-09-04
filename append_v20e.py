# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### v20e 落地（2026-08-22，全链路优化生产版）
- v20e = 事件腿（rank_score 6特征 + 回踩买点×0.99 + 分层 TP/SL）+ 延续腿（固定10日）
- 逐年：2024 +10.82%/PF 11.88 · 2025 +4.61%/PF 4.09 · 2026 +6.80%/PF 5.19
- 2026 逐月：7 月 +13.54%（WR 82%）最强
- 个股覆盖 2,808 只
- 对比 v20d：每年提升（2024 +0.51pp / 2025 +0.27pp / 2026 +0.44pp）
- 前端已同步（backtest/analysis/autopsy/kline 数据源 v20e）
- combo_v20e_trades.csv（6,891 笔）+ 组合v20e逐年逐月报告.md
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")

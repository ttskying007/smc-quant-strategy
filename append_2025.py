# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### 2025 弱市拆解（2026-08-22，审计方向②）
- 2025 事件 avg +2.83%（vs 2024 +11.43% / 2026 +7.60%）—— 全年弱
- rank 分组：rank2 +2.06% / rank3 +3.17% / rank4 +3.29% / rank5 +2.74% —— 无子集拖累，全部弱
- 皇冠 vs 非皇冠：+3.05% vs +2.82%（皇冠略优）
- 月度：1 月 +6.30% 强 / 3 月 -0.07% 弱
- **结论：2025 弱是市场 regime 问题（抄底本质在弱市弱势），非策略缺陷**
- rank 特征在弱市区分度降低（rank2-5 都在 +2-3%）—— 无有效过滤空间
- **应对：弱市降仓（资金管理层面），而非过滤信号**
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")

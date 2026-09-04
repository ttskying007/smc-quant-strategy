# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### SMC 腿恢复验证（2026-08-22，审计方向③）
- wdh 完整引擎（W1D1D4 + MAX_HOLD=5）：1,258 笔
- **avg -0.63%，胜率 57%，PF 0.77（负收益）**
- 2024 +0.23% / 2025 -0.99% / 2026 -0.75%（每年弱/负）
- 月度"互补"实为 SMC 负拖累（2026 多个月 SMC 负/事件正）
- **结论：SMC 腿（wdh 引擎）负收益，不进组合** —— 维持独立（K 线信号参考）
- 之前风控官"月度互补（8月+1.67%对冲）"基于旧数据乐观判断，实测证伪
- 之前的 MSS 模拟（78.5%/86% 胜率）是简化模拟，wdh 完整引擎实现不同（负收益）
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")

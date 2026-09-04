# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### 回踩买点可执行性（2026-08-22，审计）
- ×0.99 挂单成交率 63%（2,903/4,608）—— 大部分信号回落 1% 可成交
- 未成交 37%（开盘兜底，混合方案保证持仓）
- 成交时节省（挂单价 vs 开盘价）：中位 +0.82% / 平均 +0.69%
- **回踩买点可执行性确认**（63% 成交 + 37% 兜底，确定成交）
- 节省 0.82% 入场成本（中位）—— 对应之前 +0.47pp 增益
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")
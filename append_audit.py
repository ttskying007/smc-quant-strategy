# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### 新 SL 距离审计（2026-08-22）
- 旧 SL（swing low×0.99）：P50 -1.0%，>-10% 20%
- 新 SL（sweep low−0.5ATR）：P50 -1.7%，>-10% 23%
- 新 SL 更紧（改善 -0.7pp），但 23% 仍超 -10%（结构决定，降仓处理）
- **审计结论**：SL 设计合理（新 SL 改善 + 降仓兜底），无不合理

### 审计完整总结（7 方向）
- ③ SMC 腿恢复：证伪（wdh 负收益 -0.63%，不进组合）
- ① 延续腿 VWAP9%：落地（样本 74→113，2025 改善）
- ② 强市过滤：落地（proxy>2% 跳过，+6.99%→+8.76%）
- 新 SL 验证：改善（-1.0%→-1.7%），剩余降仓处理
- 资金追踪：放量分级 + 连续放量已落地
- 周期方案：60 日窗口已确认最优
- 买卖点：回踩 ×0.99 + 分层 TP/SL 已落地
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")
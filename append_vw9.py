# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### 延续腿 VWAP 阈值微调（2026-08-22，审计方向①）
- VWAP>8%：n=156 avg +5.94%/PF 4.77（2025 +6.99% 95笔）
- **VWAP>9%：n=113 avg +6.67%/PF 5.25（2025 +8.07% 66笔）—— 最优**
- VWAP>10%：n=74 avg +6.04%/PF 4.00（2025 +6.45% 41笔）
- 新鲜度≤5 与 ≤10 相同（VWAP 过滤隐含新鲜度）
- **落地 VWAP 10%→9%**：延续样本 74→113（+53%），组合 2025 +3.06%→+3.34%
- v20f 最终（VWAP9%）：2024 +11.36%/PF 14.07 · 2025 +3.34%/PF 5.45 · 2026 +7.52%/PF 9.57
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")

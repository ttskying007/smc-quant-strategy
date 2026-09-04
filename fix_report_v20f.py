# -*- coding: utf-8 -*-
"""修复报告一致性：v20f 新 SL 数字更新到报告"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 组合v20e报告 → 更新 v20f 数字说明
p = r"E:\test\smc_project\research\组合v20e逐年逐月报告.md"
txt = open(p, encoding="utf-8").read()
if "v20f（新SL）" not in txt:
    add = """

## 七、v20f 更新（2026-08-22 P2 后，新 SL sweep low−0.5ATR）

| 年 | v20f 新SL avg | PF |
|---|---|---|
| 2024 | +10.33% | 10.68 |
| 2025 | +4.97% | 4.35 |
| 2026 | +6.74% | 5.05 |

- 新 SL（A 股可执行）对总体影响小，2025 改善（+4.61%→+4.97%）
- v20d→v20f 受控对比（共同 4407 笔）：增量 -0.12pp（风险收益权衡，SL 更可执行）
- 皇冠（修复后）：+20.35% 中位（Bootstrap 1000/1000 正）
"""
    open(p, "a", encoding="utf-8").write(add)
    print("组合v20e报告: 已加 v20f 更新")

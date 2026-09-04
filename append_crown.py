# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### 皇冠 2024 集中根因（2026-08-22，审计）
- 2024 事件 n=2,847（占 65%）vs 2025 611 / 2026 610 —— 2024 信号供给巨大
- 2024 rank≥4 占 64%（特征强，反弹市放量/连续放量普遍）
- 2025 rank≥4 仅 32%，皇冠仅 19 笔（3%）
- **根因：市场供给问题（2024 反弹市大量强信号），非特征缺陷**
- 应用：皇冠可用于实盘，但需"信号供给感知"（弱年皇冠少 → rank≥5 或全量补充）
- 资金方案应披露年度信号供给（皇冠 2025 仅 19 笔）
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")

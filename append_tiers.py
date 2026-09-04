# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### 资金分层受控对比（2026-08-22，修复后 v20f）
- 皇冠(rank≥6)：+20.37%/WR92%/PF 59.35（2024 +22.09%(616)/2025 +3.05%(23)/2026 +8.48%(37)）
- rank≥5：+16.65%/PF 36.40（2024 1091/2025 68/2026 118 笔）
- rank≥4：+12.93%/PF 21.00（2024 1791/2025 202/2026 258 笔）
- 全部事件：+8.98%/PF 11.55 · 延续腿：+6.67%/PF 5.25 · 全量组合：+8.92%/PF 11.26
- 分层单调（皇冠最优）确认
- **弱年供给不足**：皇冠 2025 仅 23 笔（<50 万资金弱年机会极少）
- 建议：<50 万用"皇冠为主 + rank≥5 补充"（2025 68 笔）
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")

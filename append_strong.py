# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### 强市过滤（2026-08-22，审计修正方向）
- 全市场代理（200 只采样 20 日平均涨跌）分组：
  - 弱市(proxy<-2%)：+10.39%/PF 5.77（2025 +7.56%）—— 抄底甜蜜区
  - 中性(proxy<0)：+9.32%/PF 4.95
  - 强市(proxy>2%)：+1.04%/PF 1.29（无 alpha！）
- **反直觉发现**：事件腿应"强市降仓/过滤"而非"弱市降仓"（弱市是抄底甜蜜区）
- 组合级验证：过滤 proxy>2% → +6.99%→+8.76%（2025 +3.31%→+4.48%）
- **已落地**：paper_sim daily_selection 加 _market_proxy（200只采样）+ proxy>2% 事件跳过
- 修正之前"2025 弱市降仓"建议（实际应强市降仓）
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")

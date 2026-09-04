# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### P2 修复完成（2026-08-22，红蓝对抗路线图）
1. **延续腿重构**：VWAP10%（实盘已用）+ 支撑新鲜度 ≤5 天（研究：>5 天负收益 -2.43%）→ 回测 74 笔 avg +6.04%/PF 4.00（优于旧 3.87）；continuation_scanner.py 加新鲜度过滤
2. **pivot 收紧确认**：pine_like 用 swing_len 16-30（严格，无 left=2/right=1 宽松化）；LuxAlgo wave_ref size=2 是参考层非信号定义
3. **TP 单调去重 + 新 SL**：gen_v20f TP 排序去重（tp1<tp2<tp3）；SL = sweep low−0.5×ATR（v20f 重跑：2024 +10.33%/2025 +4.97%/2026 +6.74%，2025 改善）
4. **皇冠 Bootstrap + 年度拆分**：修复后合同皇冠（rank≥6 无泄漏+新SL）n=691，2024 +22.09%(WR95%)/2025 +3.05%(23笔)/2026 +8.48%(37笔)；Bootstrap 1000/1000 正中位 +20.35%（P5 +19.47%/P95 +21.28%）
5. **试点验证（决策闸门通过）**：修复后合同下皇冠依然存活（+20.35% 中位）—— 红队"皇冠可能归零"担忧未发生；但年度集中（2024 89%）需按年管理预期
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")

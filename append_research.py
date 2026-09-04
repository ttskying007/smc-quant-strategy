# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### 延续腿时间结构（2026-08-22，iter_cont_timing.py）
- 支撑形成时间：P50 0 天（92% 0-5 天）—— 延续信号本质是"新支撑回踩"
- 新支撑(0-5天)：+3.58%/PF 2.29（n=23851，好）
- 中(6-20天)：-2.43%/PF 0.56（差，负收益！n=2144）
- 旧支撑(>20天)：n=32（过小）
- 支撑越新越好（回踩后立即反弹）—— 延续信号"新鲜度"是关键
- 应用：延续腿加"支撑新鲜度"过滤（支撑≤5天）或作排序（新支撑优先）
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")

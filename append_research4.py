# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### 终极组合验证（2026-08-22，iter_ultimate.py）
- 皇冠(rank≥6) 开盘+分层：+21.20%/PF 52.48（n=428，胜率 89%）
- 皇冠(rank≥6) 回踩+分层：+21.80%/PF 60.40（n=428，最强！2024 +23.45%/2026 +8.50%）
- rank≥5 回踩+分层：+18.00%/PF 31.07（n=956）
- rank≥4 回踩+分层：+14.94%/PF 25.37（n=1757）
- 终极组合（最优排序×最优买点×最优卖点）：+21.80%/PF 60.40
- 全链路优化叠加验证通过 —— 皇冠精选（rank≥6）资金少时最佳
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")

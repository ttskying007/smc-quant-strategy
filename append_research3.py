# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### 最终 rank_score 预测力验证（2026-08-22，iter_final_rank2.py）
- rank=2：+1.81%/PF 1.49（n=1179）
- rank=3：+5.30%/PF 2.90（n=1483）
- rank=4：+8.89%/PF 4.88（n=801）
- rank=5：+12.82%/PF 8.78（n=528）
- rank≥6（皇冠）：+18.94%/PF 17.37（n=428，胜率 86%，2024 +20.51%/2025 +8.09%）
- 完美单调递增（+1.81% → +18.94%）—— 6 特征排序体系预测力验证通过
- 皇冠终极精选 = rank≥6（+18.94%/PF 17.37）
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")

# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### 大资金持续性（连续放量）研究（2026-08-22，iter_vol_cont.py）
- 单日放量(v1≥2.0)：+14.75%/PF 8.44
- 连续放量(v1≥2.0且v2≥1.5)：+15.55%/PF 9.30（n=507，更强）
- 连续放量(v1≥1.5且v2≥1.5)：+15.32%/PF 10.48（n=805，PF 最高）
- 大资金持续入场（连续 2 天放量）比单日更可靠
- 落地：rank_score 连续放量 +1（v1≥1.5 且 v2≥1.5）
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")

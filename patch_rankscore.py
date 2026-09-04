# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\paper_sim.py"
txt = open(p, encoding="utf-8").read()
old = 'rank_score = (2 if st == "ACCUM" else 1) + (1 if v_ratio > 1.2 else 0)'
new = 'rank_score = (2 if st == "ACCUM" else 1) + (1 if v_ratio > 1.2 else 0) + (1 if ("\u65b9\u6848" in str(title) or "\u9996\u6b21" in str(title) or "\u8ba1\u5212" in str(title)) else 0)'
if old in txt:
    txt = txt.replace(old, new)
    open(p, "w", encoding="utf-8").write(txt)
    print("rank_score 加事件类型 +1 完成")
else:
    print("未找到旧代码")

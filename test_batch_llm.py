# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\uzi")
from uzi_review import batch_review
stocks = [
    {"code": "600519", "name": "贵州茅台", "rank_score": 6, "stage": "ACCUM", "v_ratio": 2.5, "rr": 1.8},
    {"code": "000651", "name": "格力电器", "rank_score": 4, "stage": "DOWNTREND", "v_ratio": 1.3, "rr": 0.8},
]
r = batch_review(stocks, force=True)
for x in r:
    llm = x.get("llm") or {}
    print(f"{x['code']} {x['name']}: {str(llm)[:120]}")

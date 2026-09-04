# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\uzi")
from uzi_llm import uzi_analyze_llm

r = uzi_analyze_llm("600519", "贵州茅台", 6, "ACCUM", 2.5, 1.8, 1272, 1450, 1200)
print(f"len={len(r) if r else 0}")
print(r[:500] if r else "EMPTY")

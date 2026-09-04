# -*- coding: utf-8 -*-
import json, io, sys, os
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
research_dir = r"E:\test\smc_project\research"
files = [f for f in os.listdir(research_dir) if f.endswith(".md")]
print(f"研究报告文件 ({len(files)}):")
for f in sorted(files):
    print(f"  {f}")
print()
s = json.load(open(os.path.join(research_dir, "current_scanner_result.json"), encoding="utf-8"))
print(f"scanner: fresh={s.get('fresh_count')} coverage={s.get('coverage_pct')}% latest={s.get('latest_date')}")
led = json.load(open(os.path.join(research_dir, "paper_ledger.json"), encoding="utf-8"))
print(f"ledger: {dict(Counter(t.get('status') for t in led))}")

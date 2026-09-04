# -*- coding: utf-8 -*-
import json, io, sys, os, time
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

print("=== 系统完整状态 ===")
s = json.load(open(r"E:\test\smc_project\research\current_scanner_result.json", encoding="utf-8"))
print(f"scanner: latest={s.get('latest_date')} coverage={s.get('coverage_pct')}%")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
print(f"ledger: {dict(Counter(t.get('status') for t in led))}")
dash = json.load(open(r"E:\test\smc_project\research\combo_dashboard.json", encoding="utf-8"))
print(f"dashboard: version={dash.get('version')} n={dash.get('total_trades')}")
for y in dash.get("yearly", []):
    if y.get("year") in ("2024", "2025", "2026"):
        print(f"  {y['year']}: avg={y['avg']:+.2f}% PF={y['pf']}")

print("\n=== 研究文件 ===")
research = r"E:\test\smc_project\research"
mds = [f for f in os.listdir(research) if f.endswith(".md")]
print(f"报告文件: {len(mds)} 份")

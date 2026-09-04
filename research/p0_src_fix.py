# -*- coding: utf-8 -*-
"""任务2: src='?' 修复 —— v20c CSV 的 '?' 腿标注为 SMC + 报告勘误"""
import csv, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

p = r"E:\test\smc_project\research\combo_v20c_trades.csv"
rows = []
with open(p, encoding="utf-8-sig") as fh:
    reader = csv.DictReader(fh)
    fields = reader.fieldnames
    for r in reader:
        rows.append(r)

n_q = 0
for r in rows:
    if r.get("src") == "?":
        r["src"] = "SMC"
        n_q += 1

with open(p, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    for r in rows:
        w.writerow(r)
print(f"v20c CSV: {n_q} 笔 '?' → SMC")

# 勘误报告
from collections import Counter
print("v20c 腿分布（修复后）:", dict(Counter(r["src"] for r in rows)))

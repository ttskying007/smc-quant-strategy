# -*- coding: utf-8 -*-
"""_f7_verify.py —— 60min 刷新完成后验证: 新鲜度分布"""
import glob, io, json, os, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KT60 = r"E:\test\smc_project\hermes\kline_cache_60min"
files = glob.glob(os.path.join(KT60, "*.json"))
dates = Counter()
for fp in files[:5000]:
    try:
        j = json.load(open(fp, encoding="utf-8"))
        dates[str(j[-1].get("t") or "")[:8]] += 1
    except Exception:
        continue
top = sorted(dates.items(), reverse=True)[:6]
print("末bar 分布 top6:", {k: v for k, v in top})
d110 = dates.get("20260911", 0)
print(f"到 0911: {d110}/{len(dates)}")
# -*- coding: utf-8 -*-
"""Find which cache dirs the dashboard/kline code actually reads."""
import os, re

SCRIPTS = r"E:\test\smc_project\hermes\scripts"
targets = ["kline_cache", "intraday_cache", "pit_cache", "crawl_data", "baostock", "smc_source"]
cache_names = ["kline_cache_15min", "kline_cache_60min", "kline_cache_etf", "kline_cache_weekly", "kline_cache_v11", "kline_cache", "intraday_cache", "pit_cache"]

files = []
for dp, dn, fn in os.walk(SCRIPTS):
    dn[:] = [d for d in dn if d != "__pycache__"]
    for f in fn:
        if f.endswith(".py"):
            files.append(os.path.join(dp, f))

# which files reference which cache dir
usage = {}
for p in files:
    try:
        txt = open(p, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    for c in cache_names:
        if c in txt:
            usage.setdefault(c, []).append(os.path.relpath(p, SCRIPTS))

for c in cache_names:
    hits = usage.get(c, [])
    print("== %s: %d files" % (c, len(hits)))
    for h in hits[:8]:
        print("    ", h)

# specifically in smc_unified.py and v517_frontend_adapter.py
print("\n== smc_unified.py cache refs:")
txt = open(os.path.join(SCRIPTS, "smc_unified.py"), encoding="utf-8", errors="replace").read()
for m in re.findall(r"['\"](/root/\.hermes/[^'\"]*(?:kline|intraday|pit)[^'\"]*)['\"]", txt):
    print("    ", m)

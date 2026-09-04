# -*- coding: utf-8 -*-
"""Test Eastmoney refresh speed on 50 stocks (2 workers, 0.3s delay)."""
import io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\wdh")
import pull_eastmoney_daily as pe

# take first 50 symbols
OUT = pe.OUT
symbols = []
for f in sorted(os.listdir(OUT)):
    if f.endswith("_daily_800.json"):
        symbols.append(f.replace("_daily_800.json", "").replace("_", ".", 1))
    if len(symbols) >= 50:
        break

# force overwrite: temporarily disable skip by deleting files
import concurrent.futures
t0 = time.time()
ok = 0
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    futs = {ex.submit(pe.fetch, s): s for s in symbols}
    for fut in concurrent.futures.as_completed(futs):
        sym, n, err = fut.result()
        if n:
            ok += 1
print(f"50 stocks: {ok} ok in {time.time()-t0:.0f}s ({len(symbols)} total)")
# check latest
raw = json.load(open(os.path.join(OUT, "600519_SH_daily_800.json"), encoding="utf-8"))
print("600519 latest:", raw[-1].get("t"), "bars:", len(raw))

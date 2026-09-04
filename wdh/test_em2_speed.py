# -*- coding: utf-8 -*-
"""Test full-market Sina refresh speed (cooldown passed): 200 stocks, workers=3.
If OK, wire into daily_combo_run before scanner."""
import io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\wdh")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import concurrent.futures
import pull_sina_daily as ps

OUT = ps.OUT
symbols = []
for f in sorted(os.listdir(OUT)):
    if f.endswith("_daily_800.json"):
        symbols.append(f.replace("_daily_800.json", "").replace("_", ".", 1))
    if len(symbols) >= 200:
        break

t0 = time.time()
ok = 0
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
    futs = {ex.submit(ps.fetch, s): s for s in symbols}
    for fut in concurrent.futures.as_completed(futs):
        sym, n, err = fut.result()
        if n:
            ok += 1
print(f"200 stocks: {ok} ok in {time.time()-t0:.0f}s", flush=True)
# latest date check
raw = json.load(open(os.path.join(OUT, "600519_SH_daily_800.json"), encoding="utf-8"))
print("600519 latest:", raw[-1].get("t"))

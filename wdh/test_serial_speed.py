# -*- coding: utf-8 -*-
"""Serial Sina refresh speed test (datalen=800): 300 stocks."""
import io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\wdh")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pull_sina_daily as ps

OUT = ps.OUT
symbols = []
for f in sorted(os.listdir(OUT)):
    if f.endswith("_daily_800.json"):
        symbols.append(f.replace("_daily_800.json", "").replace("_", ".", 1))
    if len(symbols) >= 300:
        break

t0 = time.time()
ok = 0
for i, sym in enumerate(symbols):
    s, n, err = ps.fetch(sym)
    if n:
        ok += 1
    if (i + 1) % 50 == 0:
        print(f"  {i+1}/300 ok={ok} {time.time()-t0:.0f}s", flush=True)
print(f"300 stocks serial: {ok} ok in {time.time()-t0:.0f}s", flush=True)
raw = json.load(open(os.path.join(OUT, "600519_SH_daily_800.json"), encoding="utf-8"))
print("600519 latest:", raw[-1].get("t"), "bars:", len(raw))

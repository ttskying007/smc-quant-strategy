# -*- coding: utf-8 -*-
"""Eastmoney serial speed test: 300 stocks (0.15s delay, datalen via beg/end)."""
import io, json, os, sys, time, urllib.request
sys.path.insert(0, r"E:\test\smc_project\wdh")
import pull_eastmoney_daily as pe
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUT = pe.OUT
symbols = []
for f in sorted(os.listdir(OUT)):
    if f.endswith("_daily_800.json"):
        symbols.append(f.replace("_daily_800.json", "").replace("_", ".", 1))
    if len(symbols) >= 300:
        break

t0 = time.time()
ok = 0
fail = 0
for i, sym in enumerate(symbols):
    s, n, err = pe.fetch(sym)
    if n:
        ok += 1
    else:
        fail += 1
    if (i + 1) % 50 == 0:
        print(f"  {i+1}/300 ok={ok} fail={fail} {time.time()-t0:.0f}s", flush=True)
print(f"300 stocks EM serial: {ok} ok, {fail} fail in {time.time()-t0:.0f}s", flush=True)

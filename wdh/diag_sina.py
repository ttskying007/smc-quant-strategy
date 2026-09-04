# -*- coding: utf-8 -*-
"""Diagnose pull_sina_daily: run fetch for 3 symbols directly, print results."""
import io, json, os, sys
sys.path.insert(0, r"E:\test\smc_project\wdh")
import pull_sina_daily as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

for sym in ("600519.SH", "000001.SZ", "300750.SZ"):
    s, n, err = ps.fetch(sym)
    print(f"{sym}: n={n} err={err}")
    if n:
        raw = json.load(open(os.path.join(ps.OUT, sym.replace(".", "_") + "_daily_800.json"), encoding="utf-8"))
        print(f"  latest: {raw[-1].get('t')}, bars: {len(raw)}")

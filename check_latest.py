# -*- coding: utf-8 -*-
import json, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
# check latest date from a few files
for f in ("600519_SH_daily_800.json", "000001_SZ_daily_800.json"):
    p = os.path.join(KT, f)
    if os.path.exists(p):
        raw = json.load(open(p, encoding="utf-8"))
        dates = [str(r.get("t"))[:8] for r in raw if r.get("t")]
        print(f, "bars:", len(raw), "latest:", max(dates))

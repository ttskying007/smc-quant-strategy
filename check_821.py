# -*- coding: utf-8 -*-
import json, io, sys, os, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
kt = r"E:\test\smc_project\hermes\kline_cache_tencent"
latest = ""
count = 0
for f in glob.glob(os.path.join(kt, "*_daily_800.json")):
    try:
        raw = json.load(open(f, encoding="utf-8"))
        if raw and str(raw[-1].get("t", "")) > latest:
            latest = str(raw[-1].get("t", ""))
        if str(raw[-1].get("t", "")) == "20260821":
            count += 1
    except Exception:
        pass
print(f"K线最新: {latest} | 含 8/21: {count} 只")

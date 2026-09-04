# -*- coding: utf-8 -*-
import io, json, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\announce")
import pull_announce as pa

days = pa.trading_days()
print("trading days:", len(days), "first:", days[:3], "last:", days[-3:])
total, rows = pa.fetch_day(days[0], 1, 50)
print("first day:", days[0], "-> total:", total, "rows:", len(rows) if isinstance(rows, list) else rows)
if isinstance(rows, list) and rows:
    a = rows[0]
    print("sample:", str(a.get("title"))[:60], "|", a.get("art_code"))

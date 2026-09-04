# -*- coding: utf-8 -*-
import json, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
geli = [t for t in led if t.get("code") == "000651"]
print("格力电器 ledger:", json.dumps(geli[0], ensure_ascii=False)[:300] if geli else "无")
# check kline date
raw = json.load(open(r"E:\test\smc_project\hermes\kline_cache_tencent\000651_SZ_daily_800.json", encoding="utf-8"))
dates = [str(r.get("t")) for r in raw]
print("格力 K 线最新日期:", dates[-1] if dates else "无", "| 含20260819:", "20260819" in dates)

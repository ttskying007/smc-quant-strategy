# -*- coding: utf-8 -*-
import csv, io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        trades.append(r)
print("trades:", len(trades))
t = trades[0]
print("样例:", t.get("symbol"), t.get("entry_date"), t.get("net_pnl_pct"))
sym = t["symbol"]
code, ex = sym.split(".")
fn = f"{code}_{ex}_daily_800.json"
print("file:", fn, "exists:", os.path.exists(os.path.join(KT, fn)))
raw = json.load(open(os.path.join(KT, fn), encoding="utf-8"))
print("bars:", len(raw))
print("bar dates sample:", [str(r.get("t"))[:8] for r in raw[-3:]])
print("entry_date:", str(t["entry_date"]))
print("entry in dates:", any(str(r.get("t"))[:8] == str(t["entry_date"]) for r in raw))

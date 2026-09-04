# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
active = [t for t in led if t.get("status") != "CLOSED"]
print(f"活跃持仓 {len(active)} 笔\n")
tps = []
sls = []
for t in active:
    ep = t.get("entry_price") or 1
    tp = t.get("tp_price") or 0
    sl = t.get("sl_price") or 0
    if tp > 0:
        tps.append((tp / ep - 1) * 100)
    if sl > 0:
        sls.append((sl / ep - 1) * 100)

if tps:
    tps_s = sorted(tps)
    print(f"TP 分布: min={min(tps):+.1f}% p25={tps_s[len(tps_s)//4]:+.1f}% med={tps_s[len(tps_s)//2]:+.1f}% p75={tps_s[3*len(tps_s)//4]:+.1f}% max={max(tps):+.1f}%")
    print(f"TP >15%: {sum(1 for x in tps if x > 15)} 笔 ({100*sum(1 for x in tps if x > 15)/len(tps):.0f}%)")
    print(f"TP >20%: {sum(1 for x in tps if x > 20)} 笔 ({100*sum(1 for x in tps if x > 20)/len(tps):.0f}%)")
if sls:
    sls_s = sorted(sls)
    print(f"SL 分布: min={min(sls):+.1f}% med={sls_s[len(sls_s)//2]:+.1f}% max={max(sls):+.1f}%")
    print(f"SL <-15%: {sum(1 for x in sls if x < -15)} 笔")

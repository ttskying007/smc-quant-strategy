# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
print("总持仓:", len(led))
if led:
    t = led[0]
    print("\n样例字段:", list(t.keys()))
    print("样例值:", json.dumps(t, ensure_ascii=False)[:400])
    # check if any have tp/sl/signal fields
    has_tp = any("tp" in k.lower() for t in led for k in t.keys())
    has_sl = any("sl" in k.lower() for t in led for k in t.keys())
    has_signal = any("signal" in k.lower() for t in led for k in t.keys())
    print(f"\n含TP字段: {has_tp} | 含SL字段: {has_sl} | 含signal字段: {has_signal}")

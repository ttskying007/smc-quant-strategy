# -*- coding: utf-8 -*-
"""Migrate legacy OPEN entries (74) to new sim format with TP/SL + dedupe."""
import io, json, os, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = ps.load_ledger()
# dedupe: remove duplicate (code, signal_date) keeping first
seen = {}
dedup = []
for t in led:
    key = (t.get("code"), t.get("signal_date", ""))
    if key in seen:
        continue
    seen[key] = True
    dedup.append(t)
print(f"去重: {len(led)} -> {len(dedup)}")

# backfill legacy OPEN (no signal_combo / no tp/sl) with structural TP/SL
filled_count = 0
for t in dedup:
    if t.get("status") == "OPEN" and not t.get("tp_price"):
        code = t["code"]
        signal_date = str(t.get("disclose_date", "")).replace("-", "")
        tp, sl = ps.structural_sltp(code, signal_date)
        ep = t.get("entry_price", 0)
        if tp is None or sl is None:
            tp = ep * 1.15
            sl = ep * 0.90
        t["tp_price"] = round(tp, 3)
        t["sl_price"] = round(sl, 3)
        t["signal_combo"] = t.get("source", "EVENT") + "_LEGACY"
        t["signal_date"] = t.get("disclose_date", "")
        t["trigger"] = "旧逻辑T+1开盘买入（迁移）"
        # keep OPEN status but now has TP/SL; monitor will handle
        filled_count += 1
print(f"补 TP/SL 的旧持仓: {filled_count}")
ps.save_ledger(dedup)
from collections import Counter
print("状态:", dict(Counter(t["status"] for t in dedup)))
# sample
for t in dedup[:3]:
    print("  ", t["code"], t["name"], "tp=", t.get("tp_price"), "sl=", t.get("sl_price"), "sig=", t.get("signal_combo"))

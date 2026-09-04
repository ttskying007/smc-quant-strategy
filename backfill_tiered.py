# -*- coding: utf-8 -*-
"""回填分层 TP/SL 字段到现有持仓（tp1/tp2/tp3/sl1）"""
import io, json, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = ps.load_ledger()
n = 0
for t in led:
    if t.get("tp1") is not None:
        continue
    ep = t.get("entry_price") or t.get("filled_price") or 0
    if ep <= 0:
        continue
    tp = t.get("tp_price") or 0
    sl = t.get("sl_price") or 0
    t["tp1"] = round(ep * 1.05, 3)
    t["tp2"] = round(ep * 1.10, 3)
    t["tp3"] = round(tp, 3) if tp > ep * 1.10 else round(ep * 1.15, 3)
    t["sl1"] = round(sl, 3) if sl > 0 else round(ep * 0.90, 3)
    # tp_price still shows runner (original TP)
    t["tp_price"] = t["tp3"]
    n += 1
ps.save_ledger(led)
print(f"回填 {n} 笔分层 TP/SL")
from collections import Counter
print("ledger:", dict(Counter(t.get("status") for t in led)))
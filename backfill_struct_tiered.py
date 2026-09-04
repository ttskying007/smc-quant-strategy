# -*- coding: utf-8 -*-
"""回填结构分层 TP/SL：现有持仓用 SMC 结构（近→远 swing high + swing low）"""
import io, json, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = ps.load_ledger()
n = 0
for t in led:
    code = t.get("code")
    sig = str(t.get("signal_date", "") or t.get("disclose_date", ""))
    sig8 = sig.replace("-", "")
    tp1, tp2, tp3, sl = ps.structural_sltp(code, sig8)
    if tp1 is None or sl is None:
        continue
    ep = t.get("entry_price") or t.get("filled_price") or 0
    if ep <= 0:
        continue
    if tp3 <= ep:
        tp3 = round(ep * 1.15, 3)
        if tp2 <= ep:
            tp2 = round(ep * 1.06, 3)
        if tp1 <= ep:
            tp1 = round(ep * 1.03, 3)
    t["tp1"] = round(tp1, 3)
    t["tp2"] = round(tp2, 3)
    t["tp3"] = round(tp3, 3)
    t["sl1"] = round(sl, 3)
    t["tp_price"] = round(tp3, 3)
    t["sl_price"] = round(sl, 3)
    n += 1
ps.save_ledger(led)
print(f"回填 {n} 笔结构分层 TP/SL")

# sample display
from collections import Counter
print("ledger:", dict(Counter(t.get("status") for t in led)))
for t in led[:3]:
    print(f"  {t.get('code')} {t.get('name')} ep={t.get('entry_price')} TP1={t.get('tp1')} TP2={t.get('tp2')} TP3={t.get('tp3')} SL={t.get('sl_price')}")

# -*- coding: utf-8 -*-
"""修正结构分层：TP1/TP2/TP3 必须 > 入场价（否则无效层级）"""
import io, json, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = ps.load_ledger()
n = 0
for t in led:
    if t.get("tp1") is None:
        continue
    ep = t.get("entry_price") or t.get("filled_price") or 0
    if ep <= 0:
        continue
    tp1, tp2, tp3 = t.get("tp1", 0), t.get("tp2", 0), t.get("tp3", 0)
    # ensure all > entry and ascending
    levels = sorted([x for x in (tp1, tp2, tp3) if x and x > ep])
    if not levels:
        levels = [round(ep * 1.03, 3), round(ep * 1.06, 3), round(ep * 1.15, 3)]
    while len(levels) < 3:
        levels.append(round(levels[-1] * 1.03, 3))
    t["tp1"], t["tp2"], t["tp3"] = levels[0], levels[1], levels[2]
    t["tp_price"] = t["tp3"]
    n += 1
ps.save_ledger(led)
print(f"修正 {n} 笔（保证 TP 层级 > 入场价且递增）")
for t in led[:3]:
    print(f"  {t.get('code')} ep={t.get('entry_price')} TP1={t.get('tp1')} TP2={t.get('tp2')} TP3={t.get('tp3')} SL={t.get('sl_price')}")

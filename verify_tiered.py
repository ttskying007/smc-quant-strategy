# -*- coding: utf-8 -*-
"""验证结构分层执行逻辑（TP1→SL保本 / TP2→SL锁利 / TP3全部止盈）"""
import io, json, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
active = [t for t in led if t.get("status") == "FILLED"][:5]
print("=== FILLED 持仓的结构分层 ===")
for t in active:
    ep = t.get("entry_price") or 0
    print(f"  {t.get('code')} {t.get('name')} ep={ep}")
    print(f"    TP1={t.get('tp1')} (+{100*(t.get('tp1',0)/ep-1) if ep else 0:.1f}%) | TP2={t.get('tp2')} (+{100*(t.get('tp2',0)/ep-1) if ep else 0:.1f}%) | TP3={t.get('tp3')} (+{100*(t.get('tp3',0)/ep-1) if ep else 0:.1f}%) | SL={t.get('sl_price')} ({100*(t.get('sl_price',0)/ep-1) if ep else 0:.1f}%)")

# verify monitor executes without error
nf, nc = ps.realtime_monitor()
print(f"\nrealtime_monitor: 成交 {nf}, 平仓 {nc}（分层逻辑执行）")

# -*- coding: utf-8 -*-
import io, json, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
nf, nc = ps.realtime_monitor()
print(f"realtime_monitor: 成交 {nf}, 平仓 {nc}")
try:
    log = json.load(open(ps.TRADE_LOG, encoding="utf-8"))
    print(f"trade_log: {len(log)} 条")
    for r in log[-4:]:
        print(f"  {r.get('ts')} {r.get('code')} {r.get('action')} {r.get('trigger_type','-')} pnl={r.get('pnl_pct')}")
except Exception as e:
    print("trade_log:", e)

# -*- coding: utf-8 -*-
"""验证实时监控：手动执行 loop_once（检查挂单成交 + TP/SL）"""
import io, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import sim_scheduler as ss
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

print("执行 loop_once...")
nf, nc = ss.loop_once()
print(f"成交 {nf} 笔, 平仓 {nc} 笔")

# check ledger
import json
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
from collections import Counter
print("状态:", dict(Counter(t.get("status") for t in led)))
# pending orders
pending = [t for t in led if t.get("status") == "PENDING_ORDER"]
print(f"\n挂单中: {len(pending)} 笔")
for t in pending:
    print(f"  {t.get('code')} {t.get('name')} 挂单={t.get('entry_price')} sig={t.get('signal_date')}")

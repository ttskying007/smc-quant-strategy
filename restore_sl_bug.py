# -*- coding: utf-8 -*-
"""恢复错误平仓：16 笔 SL_HIT pnl=-100%（实时价=0 误触发）→ 恢复为 FILLED
（保留原 filled_price/filled_at，清除错误 exit）"""
import io, json, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = ps.load_ledger()
restored = 0
for t in led:
    if t.get("status") == "CLOSED" and t.get("exit_reason") == "SL_HIT" and t.get("pnl_pct") is not None and t.get("pnl_pct") < -90:
        # wrongly closed due to price=0 bug
        t["status"] = "FILLED"
        t["exit_reason"] = None
        t["pnl_pct"] = None
        t["note"] = "已恢复（原被实时价=0 bug 误平仓）"
        restored += 1
ps.save_ledger(led)
print(f"恢复 {restored} 笔错误平仓 → FILLED")

# verify
from collections import Counter
led2 = ps.load_ledger()
print("恢复后状态:", dict(Counter(t.get("status") for t in led2)))

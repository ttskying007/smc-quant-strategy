# -*- coding: utf-8 -*-
"""验证修复：realtime_prices 非交易时间返回 + realtime_monitor 0 价跳过"""
import io, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 1. test realtime_prices on known codes
px = ps.realtime_prices(["000651", "600519", "300637"])
print(f"realtime_prices 返回: {px}")

# 2. test realtime_monitor (should NOT close anything with 0 prices)
nf, nc = ps.realtime_monitor()
print(f"realtime_monitor: 成交 {nf}, 平仓 {nc}（应为 0，0 价跳过）")

# 3. verify ledger intact
import json
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
from collections import Counter
print("ledger:", dict(Counter(t.get("status") for t in led)))

# -*- coding: utf-8 -*-
"""现有 PENDING 挂单 → FILLED（用披露日次一日开盘价，与回测一致）
修复：挂单限价（披露日收盘）永不成交 → 开盘价直接买入"""
import io, json, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = ps.load_ledger()
converted = 0
for t in led:
    if t.get("status") != "PENDING_ORDER":
        continue
    code = t.get("code")
    sig = str(t.get("signal_date", "")).replace("-", "")
    bs = ps.bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if sig not in dates:
        continue
    i = dates.index(sig)
    entry_idx = i + 1
    if entry_idx >= len(bs):
        continue
    ep = bs[entry_idx]["o"]
    if ep <= 0:
        continue
    t["status"] = "FILLED"
    t["entry_price"] = round(ep, 3)
    t["filled_price"] = round(ep, 3)
    t["filled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    t["trigger"] = "T+1开盘买入（市价单，与回测一致）"
    # recalc TP/SL if needed (SL must be below entry)
    if t.get("sl_price", 0) >= ep:
        t["sl_price"] = round(ep * 0.90, 3)
    if t.get("tp_price", 0) <= ep:
        t["tp_price"] = round(ep * 1.15, 3)
    converted += 1
ps.save_ledger(led)
print(f"转换 {converted} 笔 PENDING → FILLED（T+1 开盘价）")

from collections import Counter
led2 = ps.load_ledger()
print("ledger:", dict(Counter(t.get("status") for t in led2)))

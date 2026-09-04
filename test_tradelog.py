# -*- coding: utf-8 -*-
import io, json, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps

# 模拟一次 BUY + SELL 日志写入
ps._append_trade_log({"ts": "2026-08-24 08:45:00", "code": "600519", "name": "贵州茅台",
                       "action": "BUY", "signal_combo": "BUYBACK_STRONG", "signal_date": "2026-08-21",
                       "entry_price": 1272.83, "tp_price": 1450.0, "sl_price": 1200.0,
                       "trigger": "T+1开盘/回踩", "pnl_pct": None})
ps._append_trade_log({"ts": "2026-08-24 08:45:05", "code": "600519", "name": "贵州茅台",
                       "action": "SELL", "signal_combo": "BUYBACK_STRONG", "signal_date": "2026-08-21",
                       "entry_price": 1272.83, "tp_price": 1450.0, "sl_price": 1200.0,
                       "trigger_type": "TP1", "pnl_pct": 3.5})
log = json.load(open(ps.TRADE_LOG, encoding="utf-8"))
print(f"trade_log: {len(log)} 条")
for r in log[-2:]:
    print(f"  {r.get('ts')} {r.get('code')} {r.get('action')} trigger={r.get('trigger_type','-')} pnl={r.get('pnl_pct')} tp={r.get('tp_price')} sl={r.get('sl_price')}")
print("字段: 时间/代码/动作/信号/TP/SL/触发/盈亏 ✅")

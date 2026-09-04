# -*- coding: utf-8 -*-
"""纸面平仓裁决准备：8-13/14/17 入场持仓的持有期 + 当前浮盈"""
import io, json, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
# 8-13/14/17 入场（sig 8-12/13/14 的事件，持有 15/20 日 → 9 月初平仓）
targets = [t for t in led if str(t.get("signal_date", "") or t.get("disclose_date", "")) in ("2026-08-12", "2026-08-13", "2026-08-14")]
print(f"8-12/13/14 信号持仓: {len(targets)} 笔\n")
for t in targets:
    sig = str(t.get("signal_date", ""))
    status = t.get("status")
    mp = t.get("mark_pnl_pct")
    mp_s = f"{mp:+.2f}%" if mp is not None else "-"
    print(f"  {t.get('code')} {t.get('name')} sig={sig} {status} 浮盈={mp_s}")

# overall status
print("\n状态分布:", dict(Counter(t.get("status") for t in led)))

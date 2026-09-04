# -*- coding: utf-8 -*-
"""纸面裁决准备：8/12-14 信号持仓的 15 日到期日计算（8/27-9/4 平仓裁决）"""
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
open_old = [t for t in led if t.get("status") == "OPEN" and str(t.get("signal_date", "") or t.get("disclose_date", "")) <= "2026-08-14"]
print(f"8-12/13/14 OPEN 持仓: {len(open_old)} 笔（15 日到期 → 8/27-9/4 平仓裁决）\n")

import datetime
for t in open_old[:10]:
    sig = str(t.get("signal_date", "") or t.get("disclose_date", ""))
    try:
        d = datetime.date(int(sig[:4]), int(sig[5:7]), int(sig[8:10]))
        expire = d + datetime.timedelta(days=15)
        mp = t.get("mark_pnl_pct")
        mp_s = f"{mp:+.2f}%" if mp is not None else "-"
        print(f"  {t.get('code')} {t.get('name')} sig={sig} → 到期 {expire} 浮盈={mp_s} TP1触发={t.get('tp1_hit','否')}")
    except Exception:
        pass

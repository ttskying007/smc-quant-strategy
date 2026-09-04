# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
# 8-21 披露的事件在 ledger 吗？
sig8_21 = [t for t in led if str(t.get("signal_date", "") or t.get("disclose_date", "")) == "2026-08-21"]
print(f"8-21 信号在 ledger: {len(sig8_21)} 笔")
for t in sig8_21:
    print(f"  {t.get('code')} {t.get('name')} {t.get('status')} rank={t.get('rank_score')}")
print(f"\nledger 状态: {dict(Counter(t.get('status') for t in led))}")
print(f"信号日期分布(活跃):")
for t in led:
    if t.get("status") != "CLOSED":
        sd = str(t.get("signal_date", "") or t.get("disclose_date", ""))
        pass
from collections import defaultdict
by_d = defaultdict(int)
for t in led:
    if t.get("status") != "CLOSED":
        by_d[str(t.get("signal_date", "") or t.get("disclose_date", ""))] += 1
print(dict(sorted(by_d.items())))

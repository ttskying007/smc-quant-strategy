# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter, defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
print(f"总 {len(led)} 笔 | 状态: {dict(Counter(t.get('status') for t in led))}\n")

print("=== OPEN 持仓（58 笔）===")
open_t = [t for t in led if t.get("status") == "OPEN"]
sig_dates = Counter(str(t.get("signal_date", "") or t.get("disclose_date", "")) for t in open_t)
print(f"信号日期: {dict(sorted(sig_dates.items()))}")
print(f"filled_at 缺失: {sum(1 for t in open_t if not t.get('filled_at'))}/{len(open_t)}")
print(f"source: {dict(Counter(t.get('source') for t in open_t))}")

print("\n=== FILLED 持仓（46 笔）===")
fill_t = [t for t in led if t.get("status") == "FILLED"]
sig_dates2 = Counter(str(t.get("signal_date", "") or t.get("disclose_date", "")) for t in fill_t)
print(f"信号日期: {dict(sorted(sig_dates2.items()))}")
print(f"filled_at 有: {sum(1 for t in fill_t if t.get('filled_at'))}/{len(fill_t)}")
print(f"entry_mode: {dict(Counter(t.get('entry_mode', 'unknown') for t in fill_t))}")
# sample
print("\nFILLED 样例:")
for t in fill_t[:4]:
    print(f"  {t.get('code')} {t.get('name')} sig={t.get('signal_date')} filled={t.get('filled_at')} ep={t.get('entry_price')} fillpx={t.get('filled_price')}")

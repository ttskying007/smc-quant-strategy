# -*- coding: utf-8 -*-
import json, io, sys, os
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
# compare research vs mirrors
for name, p in [
    ("research(主)", r"E:\test\smc_project\research\paper_ledger.json"),
    ("hermes镜像", r"E:\test\smc_project\hermes\smc_monitor\paper_ledger.json"),
    ("root镜像", r"E:\root\.hermes\smc_monitor\paper_ledger.json"),
]:
    if os.path.exists(p):
        led = json.load(open(p, encoding="utf-8"))
        new = [t for t in led if str(t.get("signal_date", "") or t.get("disclose_date", "")) >= "2026-08-15"]
        print(f"{name}: {len(led)} 笔 | 8-15起新信号 {len(new)}")
        for t in new[:4]:
            print(f"    {t.get('code')} {t.get('name')} sig={t.get('signal_date')} pick={t.get('pick_date')} {t.get('status')}")
    else:
        print(f"{name}: 不存在")

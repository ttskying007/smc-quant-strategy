# -*- coding: utf-8 -*-
import json, io, sys, os, time
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

for name, p in [
    ("research 主 ledger", r"E:\test\smc_project\research\paper_ledger.json"),
    ("镜像1", r"E:\test\smc_project\hermes\smc_monitor\paper_ledger.json"),
    ("镜像2", r"E:\root\.hermes\smc_monitor\paper_ledger.json"),
]:
    if os.path.exists(p):
        mt = time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(p)))
        try:
            led = json.load(open(p, encoding="utf-8"))
            print(f"{name}: {len(led)} 笔 | 状态: {dict(Counter(t.get('status') for t in led))} | 更新 {mt}")
        except Exception as e:
            print(f"{name}: 读取失败 {e}")
    else:
        print(f"{name}: 不存在")

# -*- coding: utf-8 -*-
import json, io, os, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
for name, p in [("镜像 selection", r"E:\root\.hermes\smc_monitor\selection_report.json"), ("主 selection", r"E:\test\smc_project\research\selection_report.json")]:
    if os.path.exists(p):
        mt = time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(p)))
        d = json.load(open(p, encoding="utf-8"))
        print(f"{name}: 修改 {mt} | selected_at={d.get('selected_at')} latest={d.get('data_latest_date')}")
    else:
        print(f"{name}: 不存在")

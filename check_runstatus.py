# -*- coding: utf-8 -*-
import json, io, sys, os, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\run_status.json"
if os.path.exists(p):
    mt = time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(p)))
    r = json.load(open(p, encoding="utf-8"))
    print(f"run_status 修改: {mt}")
    print(f"run_at={r.get('run_at')} data={r.get('data_latest_date')} complete={r.get('data_complete')}")
    print(f"steps: {r.get('steps')}")
else:
    print("run_status 不存在")

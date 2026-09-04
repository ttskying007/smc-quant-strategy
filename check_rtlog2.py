# -*- coding: utf-8 -*-
import json, io, sys, os, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\realtime_log.json"
log = json.load(open(p, encoding="utf-8"))
mt = os.path.getmtime(p)
print(f"realtime_log: {len(log)} 条 | 更新于 {time.strftime('%H:%M:%S', time.localtime(mt))} (当前 {time.strftime('%H:%M:%S')})")

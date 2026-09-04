# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
try:
    log = json.load(open(r"E:\test\smc_project\research\realtime_log.json", encoding="utf-8"))
    print(f"realtime_log: {len(log)} 条记录")
    for r in log[-5:]:
        print(f"  {r.get('ts')} {r.get('code')} {r.get('price')} {r.get('status')} pnl={r.get('mark_pnl_pct')}%")
except Exception as e:
    print("realtime_log:", e)

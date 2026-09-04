# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
try:
    d = json.load(open(r"E:\test\smc_project\research\refresh_progress.json", encoding="utf-8"))
    print(f"刷新进度: {d.get('done')}/{d.get('total')} ({d.get('coverage_pct')}%) 速度={d.get('speed')}/s ETA={d.get('eta_min')}分钟 当前={d.get('current')} status={d.get('status')}")
except Exception as e:
    print(f"进度文件: {e}")
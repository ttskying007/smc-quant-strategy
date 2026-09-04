# -*- coding: utf-8 -*-
import json, io, sys, os, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\refresh_progress.json"
d = json.load(open(p, encoding="utf-8"))
mt = os.path.getmtime(p)
print(f"进度文件更新于: {time.strftime('%H:%M:%S', time.localtime(mt))} 当前: {time.strftime('%H:%M:%S')}")
print(f"done={d.get('done')} total={d.get('total')} status={d.get('status')} current={d.get('current')}")
# check if python refresh processes alive
import subprocess
r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe"], capture_output=True, text=True)
print(r.stdout[:500])

# -*- coding: utf-8 -*-
"""测试 wmic 检测 sim_scheduler 进程"""
import subprocess, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
r = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'processid,commandline', '/format:list'],
                   capture_output=True, text=True, timeout=60)
found = False
for line in r.stdout.splitlines():
    if 'sim_scheduler' in line:
        print("发现:", line.strip()[:90])
        found = True
if not found:
    print("wmic 未发现 sim_scheduler（检测可能失败）")

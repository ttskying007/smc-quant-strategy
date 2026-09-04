# -*- coding: utf-8 -*-
"""测试修复后的 _pause_monitor / _resume_monitor"""
import io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
import daily_combo_run as dc
import subprocess


def monitor_count():
    r = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'processid,commandline', '/format:list'],
                       capture_output=True, text=True, timeout=60)
    n = sum(1 for line in r.stdout.splitlines() if 'sim_scheduler' in line and '--loop' in line)
    return n


print("暂停前监控数:", monitor_count())
dc._pause_monitor()
time.sleep(2)
print("暂停后监控数:", monitor_count())
dc._resume_monitor()
time.sleep(3)
print("恢复后监控数:", monitor_count())

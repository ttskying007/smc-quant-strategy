# -*- coding: utf-8 -*-
"""测试 daily_combo_run 的暂停/恢复监控逻辑"""
import io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
import daily_combo_run as dc


def monitor_running():
    import subprocess
    r = subprocess.run(["powershell", "-Command",
        "(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'sim_scheduler.*--loop' }).Count"],
        capture_output=True, text=True, timeout=60)
    return r.stdout.strip() if r.stdout else "0"


print("暂停前监控进程数:", monitor_running())
dc._pause_monitor()
time.sleep(2)
print("暂停后监控进程数:", monitor_running())
dc._resume_monitor()
time.sleep(3)
print("恢复后监控进程数:", monitor_running())

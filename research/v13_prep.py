# -*- coding: utf-8 -*-
"""Finalize v13: save trades, update dashboard/registry/report."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# re-run v13 to get trades saved (combo_v13_run didn't save) - run it first via subprocess
import subprocess
PY = r"C:\Users\Administrator\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe"
r = subprocess.run([PY, r"E:\test\smc_project\research\combo_v13_run.py"], capture_output=True, text=True, timeout=1800, cwd=r"E:\test\smc_project\research")
print(r.stdout[-800:])
if r.returncode != 0:
    print("ERR:", r.stderr[-500:])
    sys.exit(1)

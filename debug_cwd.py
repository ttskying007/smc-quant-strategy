# -*- coding: utf-8 -*-
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\hermes\scripts")
sys.path.insert(0, r"E:\test\smc_project\hermes\scripts\v25")
print("before import cwd:", os.getcwd())
import smc_unified as su
print("after import cwd:", os.getcwd())
from pathlib import Path
p = Path("/root/.hermes/smc_monitor/combo_dashboard.json")
print("path:", p)
print("exists:", p.exists())
print("abspath:", os.path.abspath(p))

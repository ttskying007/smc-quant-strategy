# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\hermes\scripts")
sys.path.insert(0, r"E:\test\smc_project\hermes\scripts\v25")
from pathlib import Path
p = Path("/root/.hermes/smc_monitor/combo_dashboard.json")
print("exists:", p.exists())
try:
    txt = p.read_text()
    print("read OK len:", len(txt))
    import json
    d = json.loads(txt)
    print("json OK keys:", list(d.keys()))
except Exception as e:
    print("ERR:", repr(e))

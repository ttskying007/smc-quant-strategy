# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\hermes\scripts")
sys.path.insert(0, r"E:\test\smc_project\hermes\scripts\v25")
import smc_unified as su
from pathlib import Path

combo = su._load_json_dict(Path('/root/.hermes/smc_monitor/combo_dashboard.json'), {})
print("combo loaded:", bool(combo), "keys:", list(combo.keys())[:6])
scan = combo.get("current_scanner") or {}
events = scan.get("event_candidates") or []
print("events:", len(events))
h = su.build_combo()
print("build_combo len:", len(h))
print("has 东南:", "东南" in h)
print("has 2026 avg 2.81:", "2.81" in h or "+2.81" in h)

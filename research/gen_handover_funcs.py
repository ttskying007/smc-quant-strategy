# -*- coding: utf-8 -*-
"""提取关键生产文件的函数清单，供交接文档引用"""
import json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

d = json.load(open(r"E:\test\smc_project\research\handover\code_map.json", encoding="utf-8"))
files = d["files"]
KEYS = ["daily_combo_run.py", "sim_scheduler.py", "current_scanner.py", "continuation_scanner.py",
        "finalize_dashboard.py", "paper_sim.py", "wdh_engine.py", "smc_unified.py",
        "gen_v20f.py", "finalize_v20f.py", "data_health_check.py"]
for k in sorted(files):
    if any(x in k for x in KEYS):
        info = files[k]
        print(f"## {k}")
        if info["classes"]:
            print("  类:", ", ".join(c["name"] for c in info["classes"]))
        for fn in info["funcs"][:30]:
            arg_s = ", ".join(fn["args"])
            print(f"  - {fn['name']}({arg_s})  {fn['doc']}")
        print()

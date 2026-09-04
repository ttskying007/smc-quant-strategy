# -*- coding: utf-8 -*-
import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = json.load(open(r"E:\test\smc_project\research\handover\code_map.json", encoding="utf-8"))
files = d["files"]
info = None
for k in files:
    if k.replace("\\", "/").endswith("smc_unified.py"):
        info = files[k]
        break
print("smc_unified 函数数:", len(info["funcs"]))
for f in info["funcs"]:
    n = f["name"]
    if n.startswith("api_") or n.startswith("get_") or n.startswith("handle_") or n.startswith("build_") or n.startswith("_build"):
        arg_s = ", ".join(f["args"])
        print(f"  {n}({arg_s})  {f['doc']}")

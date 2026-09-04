# -*- coding: utf-8 -*-
import re

paths = [
    r"E:\test\smc_project\hermes\scripts\v25\v517_frontend_adapter.py",
    r"E:\test\smc_project\hermes\scripts\smc_daily_ops.py",
    r"E:\test\smc_project\hermes\scripts\v25\v88_apply_production_contract.py",
]
for p in paths:
    try:
        txt = open(p, encoding="utf-8", errors="replace").read()
    except Exception as e:
        print("==", p, "ERR", e)
        continue
    print("==== %s  lines=%d" % (p.split("\\")[-1], txt.count("\n")))
    seen = []
    for m in re.findall(r"/root/\.hermes/[^\"'\s]+", txt):
        if m not in seen:
            seen.append(m)
    for m in seen[:12]:
        print("    ", m)
    # key assignments
    for m in re.findall(r"(ACTIVE_TRADE_FILE|ACTIVE_PICK_FILE|ACTIVE_VERSION|selector|TRADE_FILE|PICK_FILE)\s*=\s*[^\n#]{0,90}", txt)[:8]:
        print("    >", m.strip())
    print()

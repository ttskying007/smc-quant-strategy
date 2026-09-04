# -*- coding: utf-8 -*-
import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r'E:\test\smc_project\hermes\scripts\smc_unified.py'
txt = open(p, encoding="utf-8", errors="replace").read()
for pat in ["reselect", "rerun", "手动", "重新选", "refresh_btn", "scanBtn", "runScanner", "执行选股", "重选"]:
    ms = list(re.finditer(re.escape(pat), txt))
    if ms:
        print(f"=== {pat}: {len(ms)} 处 ===")
        for m in ms[:8]:
            s = max(0, m.start() - 70)
            e = min(len(txt), m.end() + 90)
            print("   ...", txt[s:e].replace("\n", " ")[:180])
        print()

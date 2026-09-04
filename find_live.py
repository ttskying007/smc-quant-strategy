# -*- coding: utf-8 -*-
import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r'E:\test\smc_project\hermes\scripts\smc_unified.py'
txt = open(p, encoding="utf-8", errors="replace").read()
i = txt.find("'/live'")
print("--- /live route ---")
print(txt[max(0, i - 150):i + 250])
for pat in ["def build_live", "def _live_page", "live_html", "live_controls"]:
    j = txt.find(pat)
    if j > 0:
        print()
        print("---", pat, "@", j, "---")
        print(txt[j:j + 400])

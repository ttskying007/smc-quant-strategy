# -*- coding: utf-8 -*-
import re
p = r'E:\test\smc_project\hermes\scripts\smc_unified.py'
txt = open(p, encoding='utf-8', errors='replace').read()
for pat in ["class='brand'", "/kline?ver=V517", "ver=V517"]:
    print("=== pattern:", pat, "===")
    for m in re.finditer(re.escape(pat), txt):
        s = max(0, m.start() - 80)
        print(repr(txt[s:m.end() + 80]))
        print("---")

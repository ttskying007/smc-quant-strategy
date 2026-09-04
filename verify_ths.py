# -*- coding: utf-8 -*-
import json, io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
for code in ["600519", "000001"]:
    p = rf"E:\test\smc_project\hermes\kline_cache_tencent\{code}_daily_800.json"
    if os.path.exists(p):
        raw = json.load(open(p, encoding="utf-8"))
        print(f"{code}: {len(raw)} 条 | 最新 {raw[-1]['t']} c={raw[-1]['c']}")

# add fuyao to health check
p = r"E:\test\smc_project\research\data_health_check.py"
txt = open(p, encoding="utf-8").read()
if "fuyao" not in txt:
    add = '''    "ths_fuyao": "https://fuyao.aicubes.cn/api/a-share/prices/snapshot?thscodes=600519.SH",'''
    txt = txt.replace('    "netease":', add + "\n    \"netease\":")
    open(p, "w", encoding="utf-8").write(txt)
    print("data_health_check 已加同花顺源")
else:
    print("已含同花顺")

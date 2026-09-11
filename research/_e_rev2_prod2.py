# -*- coding: utf-8 -*-
"""_e_rev2_prod2.py —— 生产 smc_candidates=0 vs 结构漏斗 L7_retest=159(0911) 的口径差审计
一个系统说全市场 0 个候选, 另一个说 159 个 retest —— 差在哪? 先看漏斗 L7 是"日扫描的池"还是
"长窗判定". 再抽 0911 L7 的一只重放生产 scanner 判定。"""
import json, os, sys, io
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sf = json.load(open(r"E:\test\smc_project\research\handover\structure_funnel_daily.json", encoding="utf-8"))
lat = sf["latest"]
print("结构漏斗 0911:", json.dumps(lat["funnel"], ensure_ascii=False))
dr = lat.get("drop_reasons", {})
top = sorted(dr.items(), key=lambda kv: -kv[1])[:6]
print("丢弃原因 top6:", {k[:40]: v for k, v in top})
# scanner 的判定窗(看 current_scanner 源码注释)
import subprocess
r = subprocess.run(["powershell", "-Command",
                    "Select-String -Path E:\\test\\smc_project\\research\\current_scanner.py -Pattern 'WINDOW|window|bars|lookback|回看|决策' | Select-Object -First 8 LineNumber,Line"],
                   capture_output=True, text=True, encoding="utf-8")
print(r.stdout[:1200])
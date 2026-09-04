# -*- coding: utf-8 -*-
import json, os, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
print("=== 报告（research/）===")
n = 0
for f in sorted(os.listdir(r"E:\test\smc_project\research")):
    if f.endswith(".md"):
        n += 1
print(f"  {n} 份报告")
print("=== 关键产物 ===")
for k, p in {
    "v18合同": r"E:\test\smc_project\research\v18预注册合同.md",
    "最终报告": r"E:\test\smc_project\research\SMC研究闭环最终综合报告.md",
    "v18交易": r"E:\test\smc_project\research\combo_v18_trades.csv",
    "纸面持仓": r"E:\test\smc_project\research\paper_ledger.json",
    "框架": r"E:\test\smc_project\research\策略思路全景与迭代框架.md",
}.items():
    print(f"  {k}: {'OK' if os.path.exists(p) else 'MISS'}")
reg = json.load(open(r"E:\test\smc_project\hermes\smc_monitor\production_registry.json", encoding="utf-8"))
print("=== 系统 ===")
print(f"  state={reg.get('state')} strategy={reg.get('production_strategy')}")
c = reg["research_candidates"]["COMBO_SMC_EVENT"]
print(f"  version={c.get('version')} yearly={c.get('yearly_avg')}")

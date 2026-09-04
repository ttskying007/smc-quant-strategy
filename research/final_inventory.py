# -*- coding: utf-8 -*-
"""Final research asset inventory + system state confirmation."""
import json, io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

print("=== 研究报告 ===")
for f in sorted(os.listdir(r"E:\test\smc_project\research")):
    if f.endswith(".md"):
        print(" ", f)

print("\n=== 关键数据 ===")
for k, p in {
    "v18交易": r"E:\test\smc_project\research\combo_v18_trades.csv",
    "v17交易": r"E:\test\smc_project\research\combo_v17_trades.csv",
    "纸面持仓": r"E:\test\smc_project\research\paper_ledger.json",
    "组合仪表盘": r"E:\test\smc_project\research\combo_dashboard.json",
    "registry": r"E:\test\smc_project\hermes\smc_monitor\production_registry.json",
}.items():
    ok = os.path.exists(p)
    print(f"  {k}: {'OK' if ok else 'MISSING'}")

print("\n=== 系统状态 ===")
reg = json.load(open(r"E:\test\smc_project\hermes\smc_monitor\production_registry.json", encoding="utf-8"))
print(f"  state={reg.get('state')} strategy={reg.get('production_strategy')} buy_enabled={reg.get('buy_enabled')}")
c = reg["research_candidates"]["COMBO_SMC_EVENT"]
print(f"  version={c.get('version')}")
print(f"  yearly={c.get('yearly_avg')}")

dash = json.load(open(r"E:\test\smc_project\research\combo_dashboard.json", encoding="utf-8"))
print(f"  dashboard={dash.get('version')} total_trades={dash.get('total_trades')}")
print(f"  paper={dash.get('paper_production',{}).get('version')} open={dash.get('paper_production',{}).get('open_positions')}")

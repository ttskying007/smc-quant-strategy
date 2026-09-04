# -*- coding: utf-8 -*-
import json, io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
checks = {
    "组合逐年逐月报告": r"E:\test\smc_project\research\组合策略逐年逐月报告.md",
    "研究闭环第三轮报告": r"E:\test\smc_project\research\研究闭环第三轮报告.md",
    "combo_trades": r"E:\test\smc_project\research\combo_trades.csv",
    "paper_ledger": r"E:\test\smc_project\research\paper_ledger.json",
    "production_registry": r"E:\test\smc_project\hermes\smc_monitor\production_registry.json",
}
for k, p in checks.items():
    print(f"{k}: {'OK' if os.path.exists(p) else 'MISSING'}")

d = json.load(open(r"E:\test\smc_project\research\combo_dashboard.json", encoding="utf-8"))
print("\n组合年度 (avg%):")
for y in d.get("yearly", []):
    if y["year"] in ("2024", "2025", "2026"):
        print(f"  {y['year']}: {y['avg']:+.2f}% (PF {y['pf']})")
paper = d.get("paper_production", {})
print(f"\n纸面状态: {paper.get('status')} | BUY_VALID: {paper.get('buy_valid_count')} | 持仓: {paper.get('open_positions')}")

reg = json.load(open(checks["production_registry"], encoding="utf-8"))
print(f"\nregistry: state={reg.get('state')} | strategy={reg.get('production_strategy')} | buy_enabled={reg.get('buy_enabled')}")

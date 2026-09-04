# -*- coding: utf-8 -*-
"""Research asset inventory: all reports, scripts, data, system state."""
import io, json, os, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = r"E:\test\smc_project"

reports = []
scripts = []
for root, dirs, files in os.walk(BASE):
    for f in files:
        p = os.path.join(root, f)
        rel = os.path.relpath(p, BASE)
        if f.endswith(".md"):
            reports.append(rel)
        elif f.endswith(".py") and ("research" in rel or "wdh" in rel or "announce" in rel):
            scripts.append(rel)

print("=== 研究报告（.md）===")
for r in sorted(reports):
    print(" ", r)
print(f"\n研究脚本（.py）: {len(scripts)} 个")
print("\n=== 关键数据资产 ===")
assets = {
    "腾讯全历史K线": r"E:\test\smc_project\hermes\kline_cache_tencent",
    "公告DB": r"E:\test\smc_project\announce\smc_announce.db",
    "融资融券DB": r"E:\test\smc_project\margin\smc_margin.db",
    "v10交易": r"E:\test\smc_project\research\combo_v10_trades.csv",
    "纸面持仓": r"E:\test\smc_project\research\paper_ledger.json",
    "registry": r"E:\test\smc_project\hermes\smc_monitor\production_registry.json",
}
for k, p in assets.items():
    ok = os.path.exists(p)
    size = os.path.getsize(p) / 1024 / 1024 if ok else 0
    print(f"  {k}: {'OK' if ok else 'MISSING'} ({size:.1f} MB)" if ok else f"  {k}: MISSING")

# system state
reg = json.load(open(assets["registry"], encoding="utf-8"))
print(f"\n=== 系统状态 ===")
print(f"  state: {reg.get('state')}")
print(f"  strategy: {reg.get('production_strategy')} | buy_enabled: {reg.get('buy_enabled')}")
combo = json.load(open(r"E:\test\smc_project\research\combo_dashboard.json", encoding="utf-8"))
print(f"  combo version: {combo.get('version')}")
print(f"  年度: {[(y['year'], y['avg']) for y in combo.get('yearly', []) if y['year'] in ('2024','2025','2026')]}")

# -*- coding: utf-8 -*-
"""Register COMBO strategy in production registry as research candidate.
buy_enabled stays False (fail-closed). BUY_VALID requires explicit production authorization."""
import json, io, sys, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\hermes\smc_monitor\production_registry.json"
d = json.load(open(p, encoding="utf-8"))

d["research_candidates"] = d.get("research_candidates") or {}
d["research_candidates"]["COMBO_SMC_EVENT"] = {
    "registered_at": datetime.date.today().isoformat(),
    "name": "组合策略：SMC三周期TP2-R20 + 内部人事件(增持/回购)",
    "status": "RESEARCH_CANDIDATE",
    "yearly_avg": {"2024": 2.06, "2025": 2.01, "2026": 2.81},
    "yearly_pf": {"2024": 1.58, "2025": 1.97, "2026": 1.98},
    "total_trades": 26775,
    "evidence": "research/研究闭环第三轮报告.md; 组合策略逐年逐月报告.md",
    "buy_enabled": False,
    "production_authorized": False,
    "authorization_note": "准生产需用户明确授权；当前为研究级，scanner 每日运行但 BUY_VALID 不产生",
}

# keep production_strategy null / EMPTY_BOOK until explicit authorization
d["state"] = d.get("state") or "FAIL_CLOSED_REPLAY_GATE_FAILED"
d["production_strategy"] = None
d["buy_enabled"] = False
d["combo_strategy"] = {
    "status": "RESEARCH_CANDIDATE_REGISTERED",
    "production_ready": False,
    "buy_valid_gate": "需用户授权 + scanner BUY_VALID 门禁（open in SL/TP for SMC；事件 T+1 入场）",
}

with open(p, "w", encoding="utf-8") as fh:
    json.dump(d, fh, ensure_ascii=False, indent=2)
print("registry updated:")
print("  state:", d["state"])
print("  production_strategy:", d["production_strategy"], "| buy_enabled:", d["buy_enabled"])
print("  research_candidates:", list(d.get("research_candidates", {}).keys()))

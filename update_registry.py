# -*- coding: utf-8 -*-
"""Update production registry: mark V88 REJECTED_LOOKAHEAD with reverify evidence."""
import json, io, sys, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\hermes\smc_monitor\production_registry.json"
d = json.load(open(p, encoding="utf-8"))
lineages = d.get("lineages") or {}
lineages["V88"] = "REJECTED_LOOKAHEAD: TP target used future-20-bar highs (v81._future_liquidity_target); reverify WR 80.1%->41.6%, PF 6.23->1.10, 2023/2026 avg negative; evidence V88重验报告.md (2026-08-17)"
lineages["V86"] = "REJECTED_LOOKAHEAD: same future-bar liquidity lineage feeding V88"
lineages["V85"] = "REJECTED_LOOKAHEAD: signal layer feeds V86/V88 future-bar liquidity"
d["lineages"] = lineages
d["v88_revocation"] = {
    "revoked_at": datetime.date.today().isoformat(),
    "reason": "REJECTED_LOOKAHEAD (look-ahead bias in TP target)",
    "evidence": "V88重验报告.md; reverify trades: smc_backtest_report/V88_reverify/v88_reverify_trades.csv",
    "frontend_label": "EMPTY_BOOK",
}
with open(p, "w", encoding="utf-8") as fh:
    json.dump(d, fh, ensure_ascii=False, indent=2)
print("registry updated:")
print("  state:", d.get("state"))
print("  production_strategy:", d.get("production_strategy"))
print("  lineages:", json.dumps(d.get("lineages"), ensure_ascii=False)[:300])

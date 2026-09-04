#!/usr/bin/env python3
"""
V136 lifecycle UI/API dry-run mapping.

Scope:
- Read V135 shadow lifecycle contracts only.
- Produce UI/API-ready dry-run payloads under smc_audit.
- Do NOT write production scanner/API/frontend/watchlist files.
- Keep BUY disabled: every mapped row has tradable=false and trade_action=NO_BUY.
"""
from __future__ import annotations

import json
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

V135_DIR = Path("/root/.hermes/smc_audit/v135_lifecycle_shadow_field_export_20260620")
OUT_DIR = Path("/root/.hermes/smc_audit/v136_lifecycle_ui_api_dry_run_mapping_20260620")
SMC_BASE = "http://127.0.0.1:8890"

INPUTS = {
    "all": V135_DIR / "v135_lifecycle_contract_all.json",
    "recent45": V135_DIR / "v135_lifecycle_contract_recent45.json",
    "latest_per_symbol": V135_DIR / "v135_lifecycle_contract_latest_per_symbol.json",
}

OUTCOME_FORBIDDEN = {
    "pnl_pct",
    "net_pnl_pct",
    "exit_reason",
    "exit_idx",
    "exit_date",
    "exit_price",
    "hold_bars",
    "mfe_pct",
    "mae_pct",
    "v132_delayed_pnl_pct",
    "v132_delayed_exit_reason",
    "v132_delayed_exit_idx",
    "v132_delayed_hold_bars",
}

STATUS_UI = {
    "KEEP_WATCH": {
        "status_label": "继续观察",
        "badge_color": "blue",
        "action_label": "KEEP_WATCH_ONLY",
        "priority": 20,
    },
    "CANCEL": {
        "status_label": "取消/降级",
        "badge_color": "red",
        "action_label": "CANCEL_OR_DOWNGRADE",
        "priority": 10,
    },
    "WATCH": {
        "status_label": "观察",
        "badge_color": "amber",
        "action_label": "WATCH_ONLY",
        "priority": 30,
    },
    "IGNORE": {
        "status_label": "忽略",
        "badge_color": "gray",
        "action_label": "IGNORE",
        "priority": 99,
    },
}

DISPLAY_FIELDS = [
    "symbol",
    "pick_date",
    "join_date",
    "entry_date",
    "poi_source",
    "combo_family",
    "market_state",
    "zone_low",
    "zone_high",
    "reclaim_close",
    "reclaim_close_above_zone_pct",
    "entry_chase_above_zone_pct",
    "risk_pct",
    "v85_zone_width_pct",
    "touch_to_reclaim_bars",
    "v133_t0_quality_score",
    "v133_t0_score_band",
    "v135_display_status",
    "v135_cancel_reason",
    "v135_buy_disabled_reason",
]


def load_rows(name: str) -> List[Dict[str, Any]]:
    return json.loads(INPUTS[name].read_text())


def fetch_json(path: str) -> Dict[str, Any]:
    with urllib.request.urlopen(SMC_BASE + path, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def production_snapshot() -> Dict[str, Any]:
    summary = fetch_json("/api/summary")
    contract = fetch_json("/api/picks/contract")
    return {
        "/api/summary": {
            "engine": summary.get("engine"),
            "total_trades": summary.get("total_trades"),
            "win_rate": summary.get("win_rate"),
        },
        "/api/picks/contract": {
            "tradable_active_pick_count": contract.get("tradable_active_pick_count"),
            "watch_only_count": contract.get("watch_only_count"),
            "raw_pick_file_count": contract.get("raw_pick_file_count"),
            "active_pick_count": contract.get("active_pick_count"),
            "active_picks_not_historical_all_market": contract.get("active_picks_not_historical_all_market"),
            "contract_note": contract.get("contract_note"),
        },
    }


def ui_row(row: Dict[str, Any]) -> Dict[str, Any]:
    status = row.get("v135_display_status", "IGNORE")
    ui = STATUS_UI.get(status, STATUS_UI["IGNORE"])
    picked = {k: row.get(k) for k in DISPLAY_FIELDS}
    picked.update(
        {
            "shadow_only": True,
            "tradable": False,
            "trade_action": "NO_BUY",
            "buy_enabled": False,
            "failed_reclaim_is_buy_signal": False,
            "ui_status_label": ui["status_label"],
            "ui_badge_color": ui["badge_color"],
            "ui_action_label": ui["action_label"],
            "ui_sort_priority": ui["priority"],
            "contract_source": "V135_LIFECYCLE_SHADOW_V1",
            "mapped_by": "V136_UI_API_DRY_RUN_V1",
        }
    )
    return picked


def build_payload(rows: List[Dict[str, Any]], scope: str) -> Dict[str, Any]:
    mapped = [ui_row(r) for r in rows]
    mapped.sort(key=lambda r: (r["ui_sort_priority"], str(r.get("symbol"))))
    counts = Counter(r["v135_display_status"] for r in rows)
    return {
        "contract_version": "V136_LIFECYCLE_UI_API_DRY_RUN_V1",
        "scope": scope,
        "shadow_only": True,
        "production_write": False,
        "buy_enabled": False,
        "trade_action": "NO_BUY",
        "rows": mapped,
        "summary": {
            "row_count": len(mapped),
            "status_counts": dict(counts),
            "tradable_count": sum(1 for r in mapped if r.get("tradable") is True),
            "buy_enabled_count": sum(1 for r in mapped if r.get("buy_enabled") is True),
            "no_buy_count": sum(1 for r in mapped if r.get("trade_action") == "NO_BUY"),
        },
        "tabs": {
            "keep_watch": [r for r in mapped if r.get("v135_display_status") == "KEEP_WATCH"],
            "cancel": [r for r in mapped if r.get("v135_display_status") == "CANCEL"],
            "ignore": [r for r in mapped if r.get("v135_display_status") == "IGNORE"],
            "watch": [r for r in mapped if r.get("v135_display_status") == "WATCH"],
        },
    }


def validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    rows = payload["rows"]
    leaked = sorted({k for r in rows for k in r.keys() if k in OUTCOME_FORBIDDEN})
    missing_required = []
    required = {
        "symbol",
        "v135_display_status",
        "shadow_only",
        "tradable",
        "trade_action",
        "buy_enabled",
        "failed_reclaim_is_buy_signal",
        "ui_status_label",
        "ui_badge_color",
        "ui_action_label",
    }
    for i, r in enumerate(rows):
        miss = sorted(required - set(r.keys()))
        if miss:
            missing_required.append({"row": i, "missing": miss})
    return {
        "scope": payload["scope"],
        "rows": len(rows),
        "outcome_field_leak": leaked,
        "missing_required_count": len(missing_required),
        "missing_required_examples": missing_required[:5],
        "tradable_true_count": sum(1 for r in rows if r.get("tradable") is True),
        "buy_enabled_true_count": sum(1 for r in rows if r.get("buy_enabled") is True),
        "trade_action_not_no_buy_count": sum(1 for r in rows if r.get("trade_action") != "NO_BUY"),
        "failed_reclaim_buy_signal_true_count": sum(1 for r in rows if r.get("failed_reclaim_is_buy_signal") is True),
    }


def latest_duplicate_count(rows: List[Dict[str, Any]]) -> int:
    counts = Counter((r.get("symbol"), r.get("poi_source")) for r in rows)
    return sum(1 for v in counts.values() if v > 1)


def write_report(summary: Dict[str, Any]) -> None:
    lines = [
        "# V136 Lifecycle UI/API Dry-run Mapping",
        "",
        f"Decision: `{summary['decision']}`。只生成 dry-run payload，不写生产 API / 前端 / watchlist。",
        "",
        "## 1. Scope",
        "",
        "- Input: V135 lifecycle shadow contracts.",
        "- Output: UI/API-ready dry-run JSON payloads.",
        "- Every row: `trade_action=NO_BUY`, `tradable=false`, `buy_enabled=false`, `shadow_only=true`.",
        "- No outcome fields exported.",
        "",
        "## 2. Payload summary",
        "```json",
        json.dumps(summary["payload_summary"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 3. Validation",
        "```json",
        json.dumps(summary["validation"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 4. Production snapshot",
        "```json",
        json.dumps(summary["production_snapshot"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 5. Conclusion",
        "",
        "V136 proves the V135 lifecycle contract can be mapped into UI/API dry-run payloads without creating tradable instructions. This is still display plumbing, not an entry edge. Next step, if continued, should be either a browser/API mock visual verification using this dry-run payload, or a separate no-lag entry model research branch. Do not promote KEEP_WATCH/CANCEL into BUY.",
    ]
    (OUT_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows_by_scope = {name: load_rows(name) for name in INPUTS}
    payloads = {scope: build_payload(rows, scope) for scope, rows in rows_by_scope.items()}

    for scope, payload in payloads.items():
        (OUT_DIR / f"v136_ui_api_dry_run_{scope}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    validations = {scope: validate_payload(payload) for scope, payload in payloads.items()}
    production = production_snapshot()
    payload_summary = {
        scope: {
            "rows": payload["summary"]["row_count"],
            "status_counts": payload["summary"]["status_counts"],
            "tradable_count": payload["summary"]["tradable_count"],
            "buy_enabled_count": payload["summary"]["buy_enabled_count"],
            "no_buy_count": payload["summary"]["no_buy_count"],
            "tab_counts": {k: len(v) for k, v in payload["tabs"].items()},
        }
        for scope, payload in payloads.items()
    }
    validation = {
        "by_scope": validations,
        "latest_duplicate_symbol_source_keys": latest_duplicate_count(rows_by_scope["latest_per_symbol"]),
        "production_unchanged_expected": production == {
            "/api/summary": {"engine": "V102_BALANCED_VOLUME_GATE", "total_trades": 195, "win_rate": 87.7},
            "/api/picks/contract": {
                "tradable_active_pick_count": 0,
                "watch_only_count": 49,
                "raw_pick_file_count": 49,
                "active_pick_count": 49,
                "active_picks_not_historical_all_market": True,
                "contract_note": "Scoped pick contract enabled.",
            },
        },
    }
    decision = "V136_LIFECYCLE_UI_API_DRY_RUN_MAPPING_DONE_NO_PRODUCTION_CHANGE"
    summary = {
        "decision": decision,
        "output_dir": str(OUT_DIR),
        "inputs": {k: str(v) for k, v in INPUTS.items()},
        "outputs": sorted(p.name for p in OUT_DIR.glob("v136_ui_api_dry_run_*.json")),
        "payload_summary": payload_summary,
        "validation": validation,
        "production_snapshot": production,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(summary)
    print(json.dumps({
        "decision": decision,
        "output_dir": str(OUT_DIR),
        "payload_summary": payload_summary,
        "validation": validation,
        "production_snapshot": production,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

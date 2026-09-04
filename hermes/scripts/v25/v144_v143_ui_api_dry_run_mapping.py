#!/usr/bin/env python3
"""V144 UI/API dry-run mapping for V143 lifecycle metadata.

Scope:
- Read V143 late-known lifecycle metadata only.
- Produce UI/API-ready dry-run payloads under smc_audit.
- Do NOT write production scanner/API/frontend/watchlist files.
- Keep BUY disabled: every mapped row has tradable=false and trade_action=NO_BUY.
"""
from __future__ import annotations

import json
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path("/root/.hermes")
V143_DIR = ROOT / "smc_audit" / "v143_late_known_lifecycle_metadata_export_20260621"
OUT_DIR = ROOT / "smc_audit" / "v144_v143_ui_api_dry_run_mapping_20260621"
SMC_BASE = "http://127.0.0.1:8890"

INPUTS = {
    "all": V143_DIR / "v143_lifecycle_metadata_all.json",
    "recent45": V143_DIR / "v143_lifecycle_metadata_recent45.json",
    "latest_per_symbol": V143_DIR / "v143_lifecycle_metadata_latest_per_symbol.json",
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
    "v138_pnl_pct",
    "v138_exit_reason",
    "v138_exit_idx",
    "v138_exit_price",
    "v138_hold_bars",
    "v138_mfe_pct",
    "v138_mae_pct",
    "mfe_5_pct",
    "mae_5_pct",
}

STATUS_UI = {
    "KEEP_WATCH_NO_LATE_FAILURE": {
        "status_label": "继续观察",
        "badge_color": "blue",
        "action_label": "KEEP_WATCH_ONLY",
        "priority": 20,
        "tab": "keep_watch",
    },
    "CANCEL_AFTER_ENTRY_DAY_CLOSE": {
        "status_label": "收盘后取消/降级",
        "badge_color": "red",
        "action_label": "CANCEL_AFTER_CLOSE_ONLY",
        "priority": 10,
        "tab": "cancel",
    },
    "INTRADAY_RISK_NOTE_ONLY": {
        "status_label": "盘中风险提示",
        "badge_color": "amber",
        "action_label": "RISK_NOTE_ONLY",
        "priority": 30,
        "tab": "risk_note",
    },
    "PRE_BUY_GAP_NOTE_ONLY": {
        "status_label": "买前缺口提示",
        "badge_color": "gray",
        "action_label": "PRE_BUY_NOTE_ONLY",
        "priority": 40,
        "tab": "note_only",
    },
}

DISPLAY_FIELDS = [
    "symbol",
    "pick_date",
    "join_date",
    "event_date",
    "entry_date",
    "poi_source",
    "combo_family",
    "market_state",
    "zone_low",
    "zone_high",
    "reclaim_close",
    "reclaim_idx",
    "entry_idx",
    "entry_price",
    "v140_entry_above_zone_high_pct",
    "v140_entry_above_reclaim_close_pct",
    "v140_entry_day_closes_below_zone_high",
    "v140_entry_day_retests_zone_high",
    "v140_early_zone_fail_0_2",
    "v140_no_entry_follow_through_le_1pct",
    "v141_earliest_lead_timing",
    "v141_pre_buy_cancel_available",
    "v141_intraday_cancel_only",
    "v141_close_or_later_only",
    "v143_lifecycle_status",
    "v143_lifecycle_reason",
]


def load_rows(name: str) -> list[dict[str, Any]]:
    return json.loads(INPUTS[name].read_text(encoding="utf-8"))


def fetch_json(path: str) -> dict[str, Any]:
    with urllib.request.urlopen(SMC_BASE + path, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def production_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {"available": False}
    try:
        summary = fetch_json("/api/summary")
        contract = fetch_json("/api/picks/contract")
    except Exception as exc:
        snapshot["error"] = repr(exc)
        return snapshot
    return {
        "available": True,
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


def ui_row(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("v143_lifecycle_status", "PRE_BUY_GAP_NOTE_ONLY"))
    ui = STATUS_UI.get(status, STATUS_UI["PRE_BUY_GAP_NOTE_ONLY"])
    picked = {field: row.get(field) for field in DISPLAY_FIELDS}
    picked.update(
        {
            "shadow_only": True,
            "production_write": False,
            "tradable": False,
            "trade_action": "NO_BUY",
            "buy_enabled": False,
            "failed_or_late_signal_is_buy_signal": False,
            "ui_status_label": ui["status_label"],
            "ui_badge_color": ui["badge_color"],
            "ui_action_label": ui["action_label"],
            "ui_sort_priority": ui["priority"],
            "ui_tab": ui["tab"],
            "contract_source": "V143_LATE_KNOWN_LIFECYCLE_METADATA",
            "mapped_by": "V144_UI_API_DRY_RUN_V1",
        }
    )
    return picked


def build_payload(rows: list[dict[str, Any]], scope: str) -> dict[str, Any]:
    mapped = [ui_row(row) for row in rows]
    mapped.sort(key=lambda row: (row["ui_sort_priority"], str(row.get("symbol")), str(row.get("entry_date"))))
    counts = Counter(str(row.get("v143_lifecycle_status")) for row in rows)
    tab_counts = Counter(row["ui_tab"] for row in mapped)
    return {
        "contract_version": "V144_V143_UI_API_DRY_RUN_V1",
        "scope": scope,
        "shadow_only": True,
        "production_write": False,
        "buy_enabled": False,
        "trade_action": "NO_BUY",
        "rows": mapped,
        "summary": {
            "row_count": len(mapped),
            "status_counts": dict(counts),
            "tab_counts": dict(tab_counts),
            "tradable_count": sum(1 for row in mapped if row.get("tradable") is True),
            "buy_enabled_count": sum(1 for row in mapped if row.get("buy_enabled") is True),
            "no_buy_count": sum(1 for row in mapped if row.get("trade_action") == "NO_BUY"),
        },
        "tabs": {
            tab: [row for row in mapped if row.get("ui_tab") == tab]
            for tab in ["cancel", "keep_watch", "risk_note", "note_only"]
        },
    }


def validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload["rows"]
    leaked = sorted({key for row in rows for key in row if key in OUTCOME_FORBIDDEN})
    required = {
        "symbol",
        "v143_lifecycle_status",
        "shadow_only",
        "production_write",
        "tradable",
        "trade_action",
        "buy_enabled",
        "failed_or_late_signal_is_buy_signal",
        "ui_status_label",
        "ui_badge_color",
        "ui_action_label",
        "ui_tab",
    }
    missing_required = []
    for idx, row in enumerate(rows):
        missing = sorted(required - set(row.keys()))
        if missing:
            missing_required.append({"row": idx, "missing": missing})
    return {
        "scope": payload["scope"],
        "rows": len(rows),
        "outcome_field_leak": leaked,
        "missing_required_count": len(missing_required),
        "missing_required_examples": missing_required[:5],
        "tradable_true_count": sum(1 for row in rows if row.get("tradable") is True),
        "buy_enabled_true_count": sum(1 for row in rows if row.get("buy_enabled") is True),
        "trade_action_not_no_buy_count": sum(1 for row in rows if row.get("trade_action") != "NO_BUY"),
        "failed_or_late_buy_signal_true_count": sum(
            1 for row in rows if row.get("failed_or_late_signal_is_buy_signal") is True
        ),
    }


def duplicate_count(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> int:
    counts = Counter(tuple(row.get(key) for key in keys) for row in rows)
    return sum(1 for value in counts.values() if value > 1)


def write_report(summary: dict[str, Any]) -> None:
    lines = [
        "# V144 V143 UI/API Dry-run Mapping",
        "",
        f"Decision: `{summary['decision']}`。只生成 dry-run payload，不写生产 API / 前端 / watchlist。",
        "",
        "## 1. Scope",
        "",
        "- Input: V143 late-known lifecycle metadata.",
        "- Output: UI/API-ready dry-run JSON payloads.",
        "- Every row: `trade_action=NO_BUY`, `tradable=false`, `buy_enabled=false`, `shadow_only=true`.",
        "- Failed/late lifecycle signal remains display metadata only; it is never converted into BUY.",
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
        "V144 confirms V143 lifecycle metadata can be rendered as UI/API dry-run rows without creating tradable instructions. This is still a display/monitoring contract only, not a production entry edge.",
    ]
    (OUT_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows_by_scope = {name: load_rows(name) for name in INPUTS}
    payloads = {scope: build_payload(rows, scope) for scope, rows in rows_by_scope.items()}

    outputs = []
    for scope, payload in payloads.items():
        out_path = OUT_DIR / f"v144_ui_api_dry_run_{scope}.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        outputs.append(out_path.name)

    validations = {scope: validate_payload(payload) for scope, payload in payloads.items()}
    production = production_snapshot()
    payload_summary = {
        scope: {
            "rows": payload["summary"]["row_count"],
            "status_counts": payload["summary"]["status_counts"],
            "tab_counts": payload["summary"]["tab_counts"],
            "tradable_count": payload["summary"]["tradable_count"],
            "buy_enabled_count": payload["summary"]["buy_enabled_count"],
            "no_buy_count": payload["summary"]["no_buy_count"],
        }
        for scope, payload in payloads.items()
    }
    validation = {
        "by_scope": validations,
        "latest_duplicate_symbol_count": duplicate_count(rows_by_scope["latest_per_symbol"], ("symbol",)),
        "latest_duplicate_symbol_poi_count": duplicate_count(rows_by_scope["latest_per_symbol"], ("symbol", "poi_source")),
    }
    decision = "V144_V143_UI_API_DRY_RUN_MAPPING_DONE_NO_PRODUCTION_CHANGE"
    summary = {
        "decision": decision,
        "production_write": False,
        "output_dir": str(OUT_DIR),
        "inputs": {key: str(path) for key, path in INPUTS.items()},
        "outputs": sorted(outputs),
        "payload_summary": payload_summary,
        "validation": validation,
        "production_snapshot": production,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

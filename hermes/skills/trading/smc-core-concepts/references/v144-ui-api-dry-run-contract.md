# V144 UI/API Dry-run Mapping Contract Pattern

Use this pattern when late-known lifecycle metadata, failure labels, or post-entry diagnostics need to be surfaced in the UI/API without becoming production buy instructions.

## Trigger

Apply when a workflow produces metadata such as:
- `CANCEL_AFTER_ENTRY_DAY_CLOSE`
- `KEEP_WATCH_NO_LATE_FAILURE`
- `INTRADAY_RISK_NOTE_ONLY`
- `PRE_BUY_GAP_NOTE_ONLY`
- any failed/late signal marker that is useful for display but not a proven entry edge

## Hard rule

Display metadata must not become tradable state. Every dry-run row must explicitly carry:

```json
{
  "shadow_only": true,
  "production_write": false,
  "tradable": false,
  "trade_action": "NO_BUY",
  "buy_enabled": false,
  "failed_or_late_signal_is_buy_signal": false
}
```

Top-level payload fields should repeat the same no-buy contract where applicable:

```json
{
  "shadow_only": true,
  "production_write": false,
  "buy_enabled": false,
  "trade_action": "NO_BUY"
}
```

## Recommended scopes

Generate and validate at least three scopes before any UI/API integration:

1. `all` — all lifecycle metadata rows.
2. `recent45` — recent display window.
3. `latest_per_symbol` — one latest row per symbol; assert duplicate symbol count is zero.

## Required row fields

Minimum display/API row contract:

- identity/time: `symbol`, `pick_date`, `join_date`, `event_date`, `entry_date`
- setup: `poi_source`, `combo_family`, `market_state`, `zone_low`, `zone_high`, `reclaim_close`, `entry_price`
- lifecycle: `v143_lifecycle_status`, `v143_lifecycle_reason`
- no-buy safety: `shadow_only`, `production_write`, `tradable`, `trade_action`, `buy_enabled`, `failed_or_late_signal_is_buy_signal`
- UI mapping: `ui_status_label`, `ui_badge_color`, `ui_action_label`, `ui_sort_priority`, `ui_tab`
- provenance: `contract_source`, `mapped_by`

## Validation checklist

For each scope, compute and report:

- `outcome_field_leak_count == 0`
- `missing_required_count == 0`
- `bad_no_buy_contract_count == 0`
- `tradable_true_count == 0`
- `buy_enabled_true_count == 0`
- `trade_action_not_no_buy_count == 0`
- `failed_or_late_buy_signal_true_count == 0`

Outcome fields must not leak into dry-run display payloads. Treat these as forbidden unless the payload is explicitly a backtest report, not a UI/API candidate contract:

```text
won, pnl, pnl_pct, exit_price, exit_date, exit_reason, tp_hit, sl_hit, mfe, mae, future_return, result
```

## Production isolation snapshot

Before reporting completion, take a read-only production snapshot to prove the dry-run did not affect current production:

- `/api/summary` engine and headline stats remain unchanged.
- `/api/picks/contract` still reports production pick contract state.
- No watchlist, production config, or front-end default is written.

## Reporting wording

Use precise status language:

- Correct: “UI/API dry-run mapping complete; no production write; no tradable instructions.”
- Incorrect: “candidate promoted,” “buy signal generated,” or “production-ready entry edge” unless a separate full-market signal/backtest gate proves it.

This pattern is a display/monitoring contract only. It is not evidence of alpha or a production entry edge.

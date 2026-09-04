# V45 Native event-sourced baseline and frontend sync lessons

Session context: after V44 stop-loss audit showed many losses from `DIRECT_SIGNAL_CLOSE`/chase entries, V45 Native was implemented as a correctness baseline directly from full-market K-line cache, not from V44 trade reconstruction.

## V45 Native contract

V45 Native must compile setups from a K-line event ledger:

```text
LIQUIDITY_SWEEP
→ LIQUIDITY_RECLAIM
→ MSS / CHOCH
→ POI_CREATED (OB/FVG/etc.)
→ RAW_ZONE_RETESTED
→ ENTRY_CONFIRMATION
→ ARMED
→ ENTERED
```

Required correctness checks:

```text
native_from_kline_not_v44_trade_reconstruction = true
direct_signal_close_trade_count = 0
standalone_ifvg_trade_count = 0
entry_inside_raw_zone_coverage = 1.0
entry_above_raw_high_invalid_count = 0
expired_setup_traded_count = 0
invalidated_setup_traded_count = 0
raw_display_split = true
raw_zone_present = true
```

Entry modes allowed for the strict baseline:

```text
CONFIRM_WICK_RETOUCH_RAW_HIGH
LIMIT_RETOUCH_RAW_HIGH
```

Explicitly forbidden:

```text
DIRECT_SIGNAL_CLOSE
NEXT_OPEN_IN_RAW_ZONE
CONFIRM_CLOSE_IN_RAW_ZONE
standalone IFVG
any continuation/chase fallback that did not return to the raw zone
```

## Interpretation of current V45 result

If V45 produces very few trades but passes the contract, do **not** treat that as production-ready. It is a correctness baseline, not a usable strategy, until recall is repaired without breaking the contract.

Example acceptance state:

```text
signal_correctness_contract_passed = true
recall_acceptance_passed = false
decision = REJECT_AS_PRODUCTION_STRATEGY__CORRECTNESS_PASS_RECALL_TOO_LOW
```

This means:

```text
Correctness baseline is valid.
Production strategy is rejected due to low recall.
Do not re-enable chase to inflate trade count.
```

## Frontend sync requirements

When adding a correctness baseline like V45, do not replace the existing production/history dashboard until recall passes. Instead expose it as a separate diagnostic surface.

Required endpoints/pages:

```text
/v45
/api/v45/report
/api/v45/validation
/api/v45/events
/api/v45/setups
/api/v45/trades
/api/v45/picks
```

Also add stop-loss audit surface if not already present:

```text
/stoploss
/api/stoploss/audit
```

The stoploss page should read the audit JSON and show:

```text
overall
by_entry_mode
by_signal_type
by_phase
by_sl_type
by_tp_type
loss_attribution_heuristic
worst_groups
```

## Pick contract pitfall

Never show historical per-symbol best trades as active picks. Keep the scopes distinct:

```text
/api/picks          = ACTIVE_CANDIDATE only
/api/picks/history  = HISTORICAL_BEST only
/api/picks/contract = counts + contract note
```

For V45-style engines, active monitoring should come from setup state, not only completed trades. Generate a watchlist with states:

```text
WAITING_FOR_RETEST
RETESTED_WAITING_CONFIRM
ARMED_READY
INVALIDATED
EXPIRED
```

Recommended file:

```text
v45_watchlist.json
```

## Recall repair direction

Use V45 as the correctness base and repair recall only via correctness-preserving mechanisms:

1. Add independent continuation branch:

```text
Trend impulse → BOS continuation → pullback POI → raw zone retest → continuation confirmation → armed
```

2. Split POI into structural raw zone and execution sub-zone:

```text
raw zone = invalidation/structure definition
execution sub-zone = smaller tradable band inside raw zone
```

3. Extend confirmation types only if they are still zone-bound and structure-bound:

```text
WICK_RECLAIM_AND_HOLD
TWO_BAR_REJECTION
MICRO_CHOCH_AFTER_RETEST
DISPLACEMENT_AFTER_RETEST
MIDPOINT_RECLAIM_CONFIRM
```

Do not use generic Engulf/Harami/Pierce as standalone signal types.

## Planning rule for this class of work

When the user asks whether front-end data is synced, verify separately:

```text
1. Which version ACTIVE_VERSION selects
2. Which files the active trade/pick cache reads
3. Which endpoints return active vs historical data
4. Whether new reports are JSON-only or exposed through pages
5. Whether K-line overlays use the same signal core as the backtest engine
```

Report sync status as a table: generated / frontend synced / current status.
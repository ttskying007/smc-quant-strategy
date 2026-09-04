# V66/Phase2 SL Root-Cause Audit Pattern

Use when Lei asks why live SMC/Smart Money picks are mostly hitting SL, or asks for a full architecture audit across signals, combinations, retrace entry, entry price/location, exits, TP/SL, analysis, and replay.

## Mandatory posture

- Do not answer from aggregate WR/RR alone.
- Diagnose the full chain: signal semantics → combo causality → retrace validity → entry legality → SL/TP math → backtest/live parity → ledger/review closure.
- Treat `entry_price <= sl_price`, `entry_price < zone_low`, missing zone fields, and backtest/live formula drift as hard mechanism defects, not tunable parameters.
- Report in tables with counts/ratios and code locations.

## High-value checks

### 1. Active pick validity

For active picks (`is_active_pick` or `pick_scope in ACTIVE_CANDIDATE/ACTIVE_ENTRY`) compute:

- missing `pick_date`, `select_date`, `entry_date`, `zone_type`, `zone_low`, `zone_high`, `sl`, `tp1`, `market_state`, `sweep_tag`, `retrace_depth_pct`
- `entry_price <= sl_price`
- `entry_price < zone_low`
- `risk_pct < 2.5%`
- SL approximately equal to `zone_low * 0.995`
- retrace buckets: `<30`, `30-60`, `60-90`, `90-100`
- zone/state/sweep cross-tabs

Interpretation:

- `entry_price <= sl_price` = buy is invalid before execution.
- `entry_price < zone_low` = demand zone likely invalidated; must not be treated as clean retrace.
- high `90-100` retrace share = strategy is catching breakdowns, not buying clean POI retests.

### 2. SL formula parity

Compare production scan vs backtest. A known V66/Phase2 failure mode:

```python
# production daily_scan.py — wrong for long-side buffer if it selects the higher stop
sl_price = max(sl_base, hard_floor_sl)

# backtest phase2_backtest.py — deeper stop
sl = min(sl_base, hard_floor)
```

For long trades, `max()` often pins SL near `zone_low * 0.995`, destroying ATR/structure buffer. If backtest uses `min()` and live scan uses `max()`, the backtest does not represent live execution.

### 3. Retrace entry semantics

Flag broad overlap checks such as:

```python
bar_touching_zone = (curr_lo <= dz_high) and (curr_hi >= dz_low)
```

This accepts a candle that pierced through and closed below the zone. A valid long retrace requires at minimum:

- wick touches/enters POI
- close reclaims `zone_low` (or stronger: zone midpoint)
- entry is above SL
- rejected breakdown / pinbar / MSS / bullish reclaim confirmation exists
- deep `90-100%` retrace is rejected unless reclaim confirmation is strong

### 4. OB/FVG separation

Do not let FVG and OB share one generic `zone touch → close entry → zone_low SL` path.

- OB_Bull can use retrace-to-demand semantics if OB is anchored to a real structure break and remains valid.
- FVG_Bull mitigation/fill can mean imbalance is consumed; deep FVG fill is often not equivalent to support test.
- Audit FVG share among active picks and SLs separately from OB.

### 5. Signal and combo causality

Check whether production scan uses the strict registry/Pine-aligned engine or a simplified detector. A weak pattern is:

```python
for z in zones:
    for c in confirms:
        if zbar < c.bar <= zbar + 30:
            accept combo
```

This is only temporal co-occurrence. Real SMC combo needs causality:

`liquidity event → structure shift → POI → retrace → rejection confirmation → entry`

Sweep must be directionally and spatially related to the zone/structure; a nearby sweep flag alone is not proof of smart-money sequence.

### 6. Backtest/live same-source gate

Before trusting results, verify the same implementation is used by:

- backtest
- daily scan / active picks
- live page / monitor positions
- K-line chart rendering
- ledger/review replay

Known failure mode: Phase2 backtest uses `signals_v22.detect_all_signals_v22`, while production scan uses `v25/smc_detector.detect_smc_signals`; plus SL formulas differ. This invalidates direct comparison.

### 7. Ledger/review closure

Check `positions.json`, `trade_ledger.json`, and review samples:

- OPEN / WATCH_ONLY / NEXT_DAY_PENDING counts
- BUY vs SELL ledger counts
- whether SL/TP events produce SELL rows and review samples
- whether T+1 blocks same-day exits but subsequent eligible exits are still processed

If ledger only has BUY and no SELL/review, live SL learning cannot close the loop.

## Report structure

Use this order:

1. Current system state table
2. Hard invalid active-pick defects table
3. Code-level root causes with file/line snippets
4. Quality bucket results: retrace, SL distance, zone type, sweep, market state
5. Why live SL happens: root-cause chain, not one-line parameter blame
6. P0/P1/P2 repair priorities
7. Explicit statement of what cannot be claimed yet (e.g. signal correctness, production viability) until same-source full-market replay passes

## P0 repair priorities

- Reject `entry_price <= sl_price`.
- Reject/diagnose `entry_price < zone_low` unless strong reclaim confirmation exists.
- Fix long-side SL buffer semantics and make backtest/live use the same function.
- Replace broad zone overlap with touch + reclaim + rejection confirmation.
- Split OB and FVG entry semantics.
- Unify signal registry across scan/backtest/chart/live.
- Restore SELL/review ledger closure for SL/TP root-cause learning.

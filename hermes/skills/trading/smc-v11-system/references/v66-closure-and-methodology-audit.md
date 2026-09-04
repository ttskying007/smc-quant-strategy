# V66 Closure + Methodology Audit Lessons

Use when working on V66/V6x SMC production repair, historical contamination, daily scan completeness, signal correctness, or methodology validation.

## What Was Proven Solved

- Historical production pollution must be verified from production files, not reports alone:
  - `positions.json`: no `CLOSED` rows with non-`PRODUCTION_CLEAN` sample class.
  - `closed_reviews.json`: zero diagnostic/non-clean reviews in production path.
  - `trade_ledger.json`: old diagnostic ledger rows physically quarantined or excluded.
- A label-only repair is insufficient. If old closed/review/ledger rows remain in hot production files, downstream pages and reports can keep reading them.
- Release gate must include both directions:
  - `production_reviews_clean_only`
  - `production_closed_positions_clean_only`
- Keep legacy `OPEN` / `WATCH_ONLY` rows visible for risk monitoring, but exclude them from production WR/SL metrics.

## Daily Data Completeness

Daily work should separate:

- Must refresh daily:
  - 750-day K-line cache refresh.
  - full-market daily scan.
  - latest daily candidates merge into V66 picks.
  - ops/page log regeneration.
- Does not need daily recomputation unless definitions or source data change:
  - historical V66 backtest trades.
  - historical signal snapshots.
  - provenance and sequence audits over unchanged historical trades.

Add a hard completeness gate for daily production scans:

- expected universe count
- K-line refresh success count
- missing symbol count
- stale latest-data date
- active tradable count vs watch-only count

Do not call `WATCH_ONLY` rows “active production picks”; show “tradable / watch-only” separately.

## Current V66 Evidence Pattern

A correct closure report should show, at minimum:

- Release gate pass with no failed checks.
- Sequence audit: `source_event_idx → zone_idx → retrace_index → conf_index → entry_index → exit_index` has zero violations.
- Provenance audit: all trade indices match the signal snapshot or explicit execution ids.
- T+1 audit: zero same-day exits.
- Live audit: open rows have zone, cost line, volatility class, and valid zone relation.
- Quality audit: no tiny wins, no below-2R wins, no >90-bar holds if that is the current release contract.

## Important Boundary

Existing sequence/provenance gates prove that trades are internally consistent and traceable. They do **not** prove Pine/LuxAlgo semantic correctness of every raw signal.

For signal-definition correctness, add a separate semantic audit that re-derives and checks:

- OB: from the confirmed structure/break point, scan backward to the nearest opposite candle; do not choose distant displacement-max candles.
- FVG: verify three-candle gap geometry and mitigation state.
- BOS/CHOCH: verify swing break direction, confirmation, and de-duplication.
- Sweep: verify wick sweep of liquidity level and cooldown.

## Multi-Retrace Handling

Future engines should materialize retrace rank:

- `retrace_rank=1` for first valid touch after zone.
- `retrace_rank=2..N` for subsequent touches.
- Track per-rank WR, avg PnL, SL rate, gap SL rate, and zone invalidation before entry.

Do not infer that “multiple retraces are fine” from aggregate WR. First-touch and later-touch behavior must be split.

## V66 Methodology Lessons

- FVG_Bull → BOS_Bull / REENTRY was the strongest current bucket in this session’s audit; OB buckets still worked but concentrated SL/GAP_SL losses.
- OB losses require loser replay before tightening rules: check zone break, gap behavior, weak confirmation, extension state, and market context.
- Current “adaptive” behavior is rule-based, not learning-based:
  - breakout quality gates
  - trend context / ATR / near-high / range-ATR adjustments
  - quality tier and reduced-size routing
  - trend runner and adaptive TP plan
  - WATCH_ONLY downgrade for excessive risk or stale/extended position

## Reporting Rule for Lei

For SMC closure reports, separate three statuses clearly:

1. **Tool-proven solved** — backed by production files and gate outputs.
2. **Currently behaving well** — backed by backtest/live metrics but still empirical.
3. **Not yet proven** — requires new semantic/retrace/completeness audit.

Never use WR alone as proof of signal correctness.

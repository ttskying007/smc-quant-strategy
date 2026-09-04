# V66 Semantic Gate + Retrace/Completeness Lessons

Use this reference when an SMC version has good WR/RR but the user asks whether the signal definitions are actually correct.

## Core Lesson

Do not let provenance, sequence order, or high WR substitute for semantic correctness. A trade can pass:

`source_event_idx → zone_idx → retrace_index → conf_index → entry_index → exit_index`

and still fail Pine/LuxAlgo semantics if the signal fields were produced by an overlay/gate on older trades rather than by a strict signal registry.

## Required Audit Layers

Add these as separate scripts before claiming closure:

1. **OB loss-bucket replay**
   - Replay only losing `OB_Bull` trades.
   - Classify root causes by bar evidence: `ENTRY_ABOVE_ZONE_HIGH`, `SL_NOT_BELOW_ZONE_LOW`, `OB_ZONE_NOT_BEARISH_CANDLE`, `GAP_THROUGH_SL`, `INTRADAY_SL_TOUCH`, `NORMAL_SL_AFTER_VALID_ENTRY`.
   - Treat SL/entry/zone-contract failures as mechanism defects, not parameters to tune away.

2. **Strict signal semantic audit**
   - OB: must be the nearest opposite candle scanned backward from the structure break/confirmation anchor; OB must precede the structure event.
   - FVG: must replay to three-candle geometry, e.g. bullish gap `low[i] > high[i-2]` within tolerance.
   - BOS/CHOCH: must close through a confirmed swing level, not be inferred from a later trade field.
   - MSS: must have a recent liquidity sweep precursor if that is part of the definition.
   - If strict semantic pass fails, report `BLOCK_SIGNAL_CORRECTNESS_CLAIM` even if WR is excellent.

3. **Multi-retrace rank audit**
   - Materialize `retrace_rank` for each trade within its zone.
   - Report per-rank WR, avg PnL, avg R, SL rate, and `invalidated_before_entry`.
   - For OB, later retraces often degrade sharply; prefer `OB_Bull rank0` unless a fresh full-market audit proves otherwise.
   - For FVG, rank behavior may differ; do not transfer OB conclusions to FVG without per-zone data.

4. **Daily full-market completeness gate**
   - Check requested universe count, kline OK count, failed ratio, latest-date count/ratio, ops data date, latest pick date, and daily candidate existence.
   - Separate active tradable rows from `WATCH_ONLY` rows.
   - A daily scan that produces no active picks can still be complete if latest-date coverage and candidate/watch-only accounting pass.

5. **Extra hard-gate aggregator**
   - Aggregate the four audits above into one gate.
   - Daily completeness, retrace materialization, and OB replay should pass.
   - `signal_semantic_strict_pass` must block claims of signal correctness and block production promotion if false.

## Production Decision Rule

- If completeness passes but semantic strict audit fails: the data pipeline is healthy, but the strategy version is not semantically validated.
- If semantic failures show `source_event_idx < zone_idx < conf_index` for OB trades, suspect a continuation/reentry overlay rather than LuxAlgo/Pine strict OB construction.
- Do not keep stacking gates on old result files to fix this class of issue; rebuild from the signal registry/source generator.

## Reporting Pattern For Lei

Keep the report table-driven:

- What was added (script/gate names)
- What passed
- What failed
- Blocking decision
- Minimal next repair direction

Avoid explaining away semantic failures with aggregate WR/RR.

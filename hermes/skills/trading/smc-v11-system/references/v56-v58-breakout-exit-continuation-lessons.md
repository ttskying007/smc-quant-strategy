# V56–V58 SMC Lessons: Breakout Quality, Graded Exit, Continuation, and Full-Sample Discipline

## Durable lesson

For Lei's SMC system, a version that looks excellent on a small curated trade set is not production-valid. Use small curated samples only as module validation. Production conclusions require full-market, 3-year, all-symbol generation or at least a full-market scan explaining the funnel.

## V56 — Breakout quality and sample shrinkage

Problem: V55 shrank to ~23 trades because it hard-rejected many trades with `STRUCTURAL_SL_TOO_FAR_CAP_WOULD_CREATE_BELOW_2R` / fake-tight-SL risk. Later analysis showed many rejected trades were profitable, so the issue was an over-strict pretrade gate, not necessarily bad signal quality.

Fix pattern:

1. Diagnose rejection reasons before changing thresholds.
2. Add an explicit multi-dimensional `breakout_quality_score` rather than a single hard threshold.
3. Classify trades into:
   - `A_NORMAL`: all checks pass, normal size.
   - `B_REDUCED_SIZE`: structural SL too far but breakout quality is strong enough; reduced size.
   - `C_REJECT`: chase entry, invalidated raw zone, weak confirmation, bad risk, or very weak breakout.
4. Attach fields to every trade/pick:
   - `breakout_quality_score`
   - `breakout_quality_detail`
   - `quality_tier`
   - `position_size_mult`
   - `live_pretrade_check`
5. Sort picks by tier then breakout quality.

Breakout-quality dimensions to include:

- close breakout magnitude / ATR
- candle body ratio
- volume expansion if available
- 1–3 bar reclaim/failure after breakout
- whether a valid FVG/OB/BPR/LV forms after breakout
- retest holds raw zone
- trend strength context
- fast return back into range

## V57 — Graded structure-break exit

Problem: V56 had many `SOLD_EARLY_BY_STRUCTURE_STOP` / `SOLD_EARLY_NEXT_90D` flags. A naive global delay of structure exits worsened most trades. This means not every future high means the original trade should have been held.

Fix pattern:

1. Compare original exit vs delayed-exit simulation per trade.
2. Keep V56 structure exits for most trades.
3. Only apply graded exits to selected strong continuation contexts.
4. Use a policy field such as:
   - `KEEP_V56_STRUCTURE_EXIT`
   - `B_SELECTIVE_GRADED_EXIT`
5. Graded exit should require additional confirmation such as:
   - multi-bar break confirmation
   - MA20 or equivalent structural confirmation
   - ATR-based wider structure stop
   - bounded extra hold window

Do not globally loosen exits just because closed-loop review reports future 90D upside.

## V58 — Continuation setup after correct exit

Problem: Remaining `SOLD_EARLY_NEXT_90D` often means the original structure exit was acceptable, but a new setup formed later. The correct solution is re-entry / continuation monitoring, not forcing the original trade to hold indefinitely.

Continuation pattern:

1. After a structure exit, scan the next window for bullish BOS/CHOCH/MSS.
2. After the structure event, find a new OB/FVG/BPR/LV zone.
3. Require retest/hold of raw zone.
4. Enforce risk cap.
5. Record continuation as an independent trade:
   - `trade_role = CONTINUATION`
   - `entry_type = POST_STRUCTURE_CONTINUATION`
   - `continuation_parent_id`
   - `continuation_parent_exit_date`
   - `continuation_bars_after_exit`
6. Re-run provenance and sequence audits. Continuation trades must have chronological indexes that pass audits (`zone_idx <= conf_index <= retrace_index/entry_index`).

## Full-sample discipline

When a version is derived from a small parent trade set, clearly label it as module validation. Before production promotion:

1. Use all available symbols (currently ~4905 A-share symbols) and 3-year K-lines/signals.
2. Generate a full signal snapshot count and family counts.
3. Report funnel counts:
   - raw signals
   - candidate setups
   - BQ-qualified candidates
   - active picks
   - trades
   - rejected pretrade gates
4. Treat `sample_not_too_narrow` as a production blocker unless the task is explicitly exploratory.
5. Never present 20–50 curated trades as a final production conclusion for Lei.

## Frontend/API synchronization checklist

After creating a new SMC version:

- add version paths and prefix in `smc_unified.py`
- update default `ACTIVE_VERSION`
- expose version in dropdown/backtest paths
- load trades and picks for the version
- ensure K-line highlights include the new version
- restart frontend service
- verify `/api/summary`, `/backtest`, `/api/picks`, and `/api/kline_full?...&ver=<VERSION>`

## User-facing reporting

For Lei, report:

- root cause first, not just metrics
- exact sample scope and whether it is full-market or curated
- full validation status including failed gates
- whether frontend/API/K-line/selection sync is complete
- remaining blockers before production

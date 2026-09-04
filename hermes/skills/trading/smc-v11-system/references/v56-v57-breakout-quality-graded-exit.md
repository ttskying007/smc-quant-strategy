# V56/V57 Lessons — Breakout Quality Tiers and Selective Graded Structure Exit

## Context
When SMC candidate volume became too small after strict pre-trade filtering, the root cause was not necessarily poor signal quality. In this session V55 reduced V54's 67 source trades to 23 because it hard-rejected `STRUCTURAL_SL_TOO_FAR_CAP_WOULD_CREATE_FAKE_TIGHT_SL`. Post-mortem showed many of those rejects were profitable strong-breakout trades, so the correct fix was tiering, not reverting all filters.

## Breakout quality score dimensions
For pre-trade quality, compute a `breakout_quality_score` from these eight dimensions:

1. `close_break_atr`: close breakout distance divided by ATR.
2. `body_ratio`: real body / full candle range.
3. `volume_ratio`: current volume / 20-bar average volume.
4. `no_reclaim_1_3`: whether price avoids reclaiming the break level/raw zone in the next 1-3 bars.
5. `new_zone_after_break`: whether a valid FVG/OB/BPR/LV appears after breakout.
6. `retest_holds_raw_zone`: whether retest preserves the raw zone.
7. `strong_trend`: MA/trend context score, not just price above MA.
8. `no_fast_return_to_range`: whether breakout avoids immediately falling back into the range.

## A/B/C pre-trade tiering
Use the quality score to avoid all-or-nothing filtering:

- **A_NORMAL**: clean setup and strong BQ; normal size.
- **B_REDUCED_SIZE**: structural SL is far but breakout quality is acceptable/strong; reduced size rather than hard reject.
- **C_REJECT**: chase entry, zone invalidation, weak confirmation, risk anomaly, or very low BQ; reject before order.

Important pitfall: `STRUCTURAL_SL_TOO_FAR_CAP` alone should not automatically reject if BQ supports the setup. But chase/zone-invalid/weak-confirmation issues remain hard reject; do not hide them by lowering position size.

## Selection and live-check integration
Add these fields to trades and picks and use them in real-time entry checks:

- `breakout_quality_score`
- `breakout_quality_detail`
- `quality_tier`
- `position_size_mult`
- `live_pretrade_check`

Sort picks by tier first, then descending BQ score. Live entry must obey A/B/C before order submission.

## Structure-exit lesson
Trying to delay all `STRUCT_CONFIRM_BREAK` exits is dangerous. A global runner delay improved a few trades but worsened most, lowered average PnL, and introduced avoidable drawdown. Use selective graded exits only where evidence supports extension.

A safer V57-style structure exit model:

- Keep the existing confirmed structure exit for most trades.
- Extend only selected B-tier, strong-trend trades where prior PnL and BQ band indicate continuation potential.
- For extension, require multi-bar confirmation, MA confirmation, wider ATR stop, and reclaim cancellation. Do not exit on a single noisy pierce.
- Track `old_exit_*`, `v57_exit_delta_pct`, `v57_exit_delta_bars`, `v57_graded_exit_policy`, and `v57_graded_exit_trace` to prove the modification helped.

## Diagnostic rule for SOLD_EARLY flags
`SOLD_EARLY_NEXT_90D` does not always mean the original position should have been held longer. Many cases are new continuation setups after a valid exit. Diagnose each trade as:

1. Original setup exit too early — adjust runner/structure exit.
2. Exit correct, but new setup appeared later — build continuation re-entry logic.
3. Post-exit move is not tradable from the original setup — leave unchanged.

Do not blindly widen runner logic to remove all SOLD_EARLY flags.

## Required validation
After changing entry or exit logic, run full closed-loop validation:

- full trades and picks generation;
- quality metrics;
- trade provenance audit;
- signal sequence audit;
- 90-day closed-loop review;
- sample bias audit;
- release gate;
- front-end sync checks for summary, backtest, picks, and kline APIs.

Acceptance requires no hidden regression in WR/RR, no new low-R wins, no post-hoc filtering masquerading as pre-trade gating, and visible front-end synchronization.

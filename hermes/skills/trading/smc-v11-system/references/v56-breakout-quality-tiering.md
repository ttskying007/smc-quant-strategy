# V55/V56 Breakout Quality Tiers and Sample-Width Lesson

## Trigger
Use this when an SMC version becomes too strict after moving quality filters before entry, especially when trade count collapses while historical rejected trades still show high WR/avg PnL.

## Durable lesson
A hard pre-trade gate is safer than post-trade masking, but it can become over-strict if it treats all structural risk defects as equal. Diagnose the rejected bucket before relaxing or tightening filters.

In the V55 case, the sample collapsed because `STRUCTURAL_SL_TOO_FAR_CAP_WOULD_CREATE_FAKE_TIGHT_SL` was treated as a hard reject. Most rejected trades were not necessarily low-quality; the main defect was that the full structure stop was far and the old max-risk cap could create a fake tight SL. The correct response was not to revert to post-filtering, but to split the gate into quality tiers.

## Required diagnostic before changing gates
1. Compare kept vs rejected trades:
   - trade count
   - WR
   - avg PnL
   - avg realized R
   - reject reason distribution
2. Isolate real losers and inspect their pre-entry attributes.
3. Check whether losses cluster below a breakout-quality threshold.
4. Only then convert a hard reject into a reduced-size tier.

## V56 breakout_quality_score dimensions
Score breakouts with these eight dimensions:
1. `close_break_atr`: close突破幅度 / ATR
2. `body_ratio`: 实体占比
3. `volume_ratio`: 成交量放大倍数
4. `no_reclaim_1_3`: 突破后1-3 bar是否没有reclaim
5. `new_zone_after_break`: 是否产生有效 FVG / OB / BPR / LV
6. `retest_holds_raw_zone`: retest是否守住 raw zone
7. `strong_trend`: 是否发生在强趋势状态
8. `no_fast_return_to_range`: 是否突破后马上回到range

## Tiering pattern
- A layer: no hard defects and breakout quality is strong. Normal size.
- B layer: structure SL is far or breakout quality is acceptable but not perfect. Reduced size.
- C layer: chase, invalid zone, weak confirmation, risk anomaly, or very weak breakout. Reject before order.

Important: structural SL too far is not automatically the same as invalid signal. It can be a position-sizing problem if breakout quality is strong. Chase/zone invalidation/weak confirmation remain true hard rejects.

## Frontend / live sync requirements
When adding a new SMC version:
- Add `ACTIVE_VERSION` and active trade/pick paths.
- Add version loader in `get_version_trades()` and `get_version_picks()`.
- Add `_active_version_paths()` metadata.
- Include the version in K-line signal snapshot versions so BOS/CHOCH/MSS remain visible.
- Add version option in K-line UI and backtest/run-engine maps.
- Ensure picks expose `quality_tier`, `breakout_quality_score`, `position_size_mult`, and `live_pretrade_check`.
- Sort picks by tier first, then breakout quality score.

## Acceptance gates
Do not claim release quality from aggregate WR alone. Run at minimum:
- quality metrics
- provenance audit
- signal sequence audit
- 90D closed-loop review
- sample-bias audit
- release gate

If sample count is still below threshold, report that explicitly even if WR is excellent. Treat it as a coverage warning, not a failure of the scoring idea.

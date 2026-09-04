# V185-V187 post-V175 failed-path closure

Date: 2026-06-25

## Trigger

Use when continuing SMC research after V175/V180-V184 and deciding whether to keep testing filters, breadth overlays, delayed post-reclaim candles, or raw accumulation breakout generators.

## Gates used

Research child engine usable:
- 100% non-overlap vs V175;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- `micro_profit_pct <= 1%`;
- T+1 violations = 0.

Production upgrade usable:
- combined engine `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- T+1 violations = 0;
- no frontend/watchlist/API mutation before dry-run passes.

## V185 — market breadth + pre-entry target geometry

Artifact: `/root/.hermes/smc_audit/v185_market_breadth_target_geometry_20260625_135122/`

Contract:
- Evaluation uses V129 realistic target exits, not original V128 TIME drift outcome.
- Selectors use only pre-entry/source-side fields plus previous-trading-day full-market breadth built from raw K-line cache.
- No production/frontend/watchlist writes.

Result:
- Decision: `V185_NO_PRODUCTION_OR_RESEARCH_PASS__BREADTH_TARGET_FILTER_CLOSED`.
- Passed count: 0; frontier count: 0 under the strict interesting-rule screen.
- Interpretation: simple broad-market breadth/environment permission does not rescue V128 under realistic target exits.

## V186 — micro-HL post-reclaim takeover generator

Artifact: `/root/.hermes/smc_audit/v186_micro_hl_takeover_generator_20260625_135750/`

Contract:
- Source is V128 POI/event supply, but entry is delayed until a new post-reclaim confirmation candle appears.
- Confirmation tested: low-hold above zone floor, bullish close above zone, close position/body strength, next-open entry, strict T+1 replay.
- Non-overlap vs V175 only; audit-only.

Best result:
- Variant: `max_wait=3`, `close_pos_min=0.7`, `body_min=0.4`, `hold=above_zone_low`.
- `n=603`, `WR=44.44%`, `Avg=-0.293%`, `min_year_n=51`, `all_year_WR_min=33.33%`, `micro=0.17%`, T+1=0.
- Exit mix: `TP=257`, `SL=169`, `POI_CLOSE_BREAK=139`, `GAP_SL=17`, `TIME=21`.
- Decision: `V186_NO_RESEARCH_CHILD_PASS__MICRO_TAKEOVER_CLOSED`.

Interpretation:
- Stronger post-reclaim candle confirmation changes timing but does not solve the signal-quality problem. Failures remain semantic/POI survival failures, not T+1 or field pollution.

## V187 — raw accumulation breakout retest generator

Artifact: `/root/.hermes/smc_audit/v187_fast_accumulation_breakout_retest_20260625_141203/`

Contract:
- Raw K-line generator, not V128/V167/V175 filtering.
- Pattern: accumulation range → displacement breakout → base/OB retest → later reclaim → next-open entry.
- T+1 replay; audit-only.

Best result:
- Variant: `base_len=20`, `max_range=0.1`, `breakout=0.02`, `wait=8`.
- `n=8`, `WR=50.0%`, `Avg=1.0196%`, `min_year_n=1`, T+1=0.
- Decision: `V187_NO_RESEARCH_CHILD_PASS__ACCUMULATION_BREAKOUT_RETEST_CLOSED`.

Interpretation:
- Strict raw accumulation-breakout-retest is too sparse under current daily-data constraints and does not produce a robust child engine.

## Closed paths after V185-V187

1. V128 + previous-day full-market breadth + target geometry filtering.
2. V128 delayed post-reclaim micro candle confirmation.
3. Raw accumulation breakout retest generator using daily K-line only.
4. Any promotion based only on these artifacts.

## Next valid research direction

The next qualitative path must introduce information not present in V128/V129 daily single-stock fields:

- sector/industry-synchronized confirmation or peer-breadth at entry time;
- stronger source-side institutional takeover proxy before entry, not a single confirmation candle;
- multi-timeframe data only after historical 60min coverage is filled enough for full backtest;
- or a rebuilt generator with explicit liquidity target quality and POI survival model created before entry.

Do not continue scalar slicing of V128/V167/V175 or generic exit overlays unless a genuinely new pre-entry feature is added.

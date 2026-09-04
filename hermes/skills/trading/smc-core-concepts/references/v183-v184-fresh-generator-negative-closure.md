# V183-V184 fresh generator negative closure

Date: 2026-06-25

## Trigger

Use after V175/V180-V182 closure when testing whether qualitative improvement can come from a genuinely new K-line-only SMC generator instead of filtering V128/V167/V175 artifacts.

## Predeclared usable / unusable standards

Production usable:
- Source-side, non-leaking rule;
- T+1 violations = 0;
- combined/new engine `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API writes before dry-run passes.

Research child usable:
- 100% non-overlap vs V175;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

Unusable:
- Any T+1 violation;
- WR lift caused by micro-profit/BE pollution;
- yearly instability;
- pure relabeling or filtering of existing V128/V167/V175 rows;
- apparent quality that requires outcome fields (`exit_reason`, `pnl`, `mfe/mae`, hit flags).

## Executed fresh generators

### V183 context-first BOS continuation generator

Artifact: `/root/.hermes/smc_audit/v183_context_first_fresh_generator_20260625_163211/`

Source:
- K-line cache only (`*_daily_750.json`), 4,652 scanned symbols;
- not a V128/V167/V175 filter;
- architecture: environment range permission → BOS continuation → fresh demand OB → touch/reclaim → T+1 semantic exit.

Result:
- `n=3636`
- `WR=31.35%`
- `Avg=0.3758%`
- `median=-3.9734%`
- `min_year_n=425`
- yearly WR: 2023 `21.65%`, 2024 `30.76%`, 2025 `39.52%`, 2026 `21.16%`
- `T+1 violations=1` due no-next-bar candidate on `002380.SZ 20260625`; rule must remove such entries by construction.
- exit mix: SL `2114`, GAP_SL `248`, TP `841`, TIME `383`, POI close break `50`.
- overlap with V175: `0`.
- decision: `UNUSABLE`.

Root cause:
- Fresh BOS continuation demand OB is not a valid standalone supply layer in A-share daily data. Most candidates are stopped before semantic target; continuation breakout creates a huge false-positive supply layer.
- Source-side single-feature slice search found no frontier; best RR slice only reached ~42% WR with near-flat Avg.
- Broad-market breadth gating improved V183 only to ~49% WR / Avg 3.5% in a 2024-2025-only strong breadth slice, still nowhere near yearly-stable gate and not production usable.

### V184 fresh SSL sweep → CHOCH reversal generator

Artifact: `/root/.hermes/smc_audit/v184_fresh_ssl_choch_demand_generator_20260625_163502/`

Source:
- K-line cache only, 4,649 scanned symbols;
- not a V128/V167/V175 filter;
- architecture: confirmed swing SSL sweep → CHOCH over swing high → fresh demand OB → touch/reclaim → T+1 semantic exit.

Result:
- `n=674`
- `WR=32.49%`
- `Avg=1.2796%`
- `median=-4.0560%`
- `min_year_n=71`
- yearly WR: 2023 `16.90%`, 2024 `38.25%`, 2025 `37.68%`, 2026 `22.76%`
- `T+1 violations=0`
- exit mix: SL `346`, GAP_SL `26`, TP `95`, TIME `180`, POI close break `27`.
- overlap with V175: `1`.
- decision: `UNUSABLE`.

Root cause:
- Classical-looking SSL sweep→CHOCH is still too broad without V132/V167 true-takeover quality; daily swing logic alone does not recreate V175 quality.
- Source-side slice search and breadth gates did not produce a usable child engine; best low-price slices reached only ~45% WR / Avg ~4%, with 2023 instability.

## Closed paths after V183-V184

Do not continue these without a materially new signal definition:
1. Naive fresh BOS continuation from daily K-line cache.
2. Naive fresh SSL sweep→CHOCH from daily K-line cache.
3. Single-feature source-side filtering of those fresh generators.
4. Broad-market breadth as a rescue gate for those fresh generators.

## Next direction

The next qualitative direction is not another generic daily BOS/CHOCH detector. It must either:

1. **Rebuild true-takeover semantics directly from price path** — focus on the V132/V167 mechanism that made V175 work: post-zone reclaim quality, bull-count persistence, failed-reclaim exclusion, and zone-width/pullback constraints; or
2. **Fill/extend historical 60min data** and retest TIME/entry microstructure because V179 only had `9/65 = 13.85%` TIME-row 60min coverage; or
3. **Rematerialize current V175 active picks from latest V128 snapshot** as a production-sync task, not a new strategy improvement, because latest V128 produced 27 current V172/V175-like actives while physical `v175_active_picks.json` had 26.

Research priority:
- Strategy quality: rebuild true-takeover generator from kline path with V132-like features and no outcome fields.
- Production hygiene: active-picks rematerialization after dry-run comparison.

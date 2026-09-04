# V85 MIXED_ACCUMULATION Production Lesson

Session date: 2026-06-12

## Trigger

Use this when continuing SMC signal-layer work after V84 path splitting, especially if the task asks whether `MIXED` should be rejected, whether V85 is production-ready, or whether frontend/backend data is fully synchronized.

## Mechanism lesson

V84 proved `HOLD_ABOVE_POI` is the strongest current proxy for smart-money takeover, and that continuation paths outperform reversal paths. It also revealed an apparently contradictory high-quality bucket: `post_MIXED + narrow POI`.

V85 resolved that by splitting `MIXED`:

- `MIXED_ACCUMULATION`: narrow POI + hold-above-POI + no lower-low after reclaim.
- `MIXED_DISTRIBUTION`: wide POI or post-reclaim lower-low / failed control.

Key correction: do **not** globally filter `MIXED`. Treat it as an ambiguous parent state requiring sub-classification.

## V85 production rule

Source: `/root/.hermes/smc_opt_v85_mixed_accumulation_generator/v85_candidates.json`

Production gate:

```text
1 < zone_width_pct <= 2
1 < risk_pct <= 1.5
hold_bars <= 2
takeover = HOLD_ABOVE_POI
T+1 enforced
```

Output:

- `/root/.hermes/smc_opt_v85_production_gate/v85_trades.json`
- `/root/.hermes/smc_opt_v85_production_gate/v85_picks.json`
- `/root/.hermes/smc_opt_v85_production_gate/v85_production_report.json`

## Results

| Layer | n | WR | avg_pnl | POI break | trend damage | TP rate |
|---|---:|---:|---:|---:|---:|---:|
| V85 source | 23,345 | 64.50% | +0.5609% | 17.33% | 4.04% | 78.21% |
| V85 production | 559 | 89.09% | +2.7117% | 9.30% | 1.79% | 88.91% |

By year:

| Year | n | WR | avg_pnl |
|---|---:|---:|---:|
| 2023 | 110 | 86.36% | +2.1994% |
| 2024 | 132 | 88.64% | +2.5466% |
| 2025 | 233 | 90.56% | +2.9458% |
| 2026 | 84 | 89.29% | +2.9927% |

By path:

| Path | n | WR | avg_pnl |
|---|---:|---:|---:|
| CONTINUATION_EXPANDED_HOLD_ABOVE_POI | 294 | 87.07% | +2.6387% |
| MIXED_ACCUMULATION_HOLD_ABOVE_POI | 265 | 91.32% | +2.7927% |

Production criteria passed:

- total >= 500
- each year 2023–2026 >= 50
- each year 2023–2026 WR >= 65%
- T+1 violations = 0
- field audit = 0 missing

## Remaining mechanism gaps

V85 is production-ready by backtest gate, but not complete as a full SMC theory implementation:

1. Reversal path remains weak; V84 reversal was only 10 rows / 50% WR.
2. POI close-break remains the main loss source: V85 has 52 `EXIT_POI_CLOSE_BREAK` losses.
3. Trend damage remains smaller but high-impact: 10 `EXIT_TREND_STRUCTURE_DAMAGE` rows.
4. `RECOVERY` state is weaker than `BULL_CONTINUATION` and `MIXED_ACCUMULATION`.

## Frontend/backend sync pitfall

Do not say “all frontend/backend data is fresh” just because V85 production files exist or `/api/picks` is correct.

Verified V85 state:

- `/api/picks`: V85, 559 rows, zero missing pick/join/zone/cost/volatility fields.
- `/api/live-prices`: zero field blanks, but sample rows still came from `V66_FULL_MARKET_SCAN` daily monitor state.
- `/monitor`: lower current-picks table showed V85, but upper daily-monitor table still showed V66 rows.
- `/analysis` and `/autopsy`: pages showed V85, but WR rendered as 0.0% while average PnL was positive, indicating old winner/statistics compatibility gaps.
- `/autopsy`: 90-day closed-loop review was not generated for V85.
- `/api/kline_full`: returned `version=V85` and V85 trade markers, but background `signals_list` still included `UNAUDITED` / `PENDING_REPLAY` generic signals.
- `/api/resonance`: returned rows, but 60min/hourly fields often remained `?`.

Precise completion language:

> V85 production backend and `/api/picks` are live and field-complete; full frontend/live/analysis/autopsy/resonance sync is not complete.

## Next class-level workflow

Before inventing another strategy version, run a V86 frontend/backend sync release:

1. Switch daily scan/live monitor from V66 to V85 production gate.
2. Fix `/analysis` and `/autopsy` winner/statistics compatibility with V85 rows.
3. Fill monitor quality/SL/TP display from V85 fields.
4. Generate and render V85 90-day closed-loop review.
5. Separate Kline production trade markers from unaudited background signal markers.
6. Populate weekly/daily/60min resonance fields for V85 picks.

Only after those pass should a future session claim end-to-end V85 production sync.

# V102 Monthly SL Instability Diagnostic Pattern

Use this reference when SMC monthly reports look unstable, especially when SL rate jumps between 0%, 20%, and 100% month to month.

## Reusable Lessons

1. Do not diagnose SL stability from calendar-month aggregates alone.
   - Natural months often have uneven sample sizes.
   - Months with fewer than 5 trades can show 0% or 100% SL from noise.
   - Add sample confidence labels: `n<5 observation only`, `5<=n<15 low confidence`, `n>=15 evaluable`.

2. Always separate statistical noise from real failure months.
   - First flag small-sample extremes.
   - Then isolate months with `n>=5` and high SL rate.
   - In the V102 diagnostic, real review months were `2023-07`, `2023-09`, `2023-11`, and `2026-02`; the reusable pattern is the thresholding, not those months.

3. Add rolling stability windows.
   - Generate `rolling20` and `rolling50` trade windows sorted by `entry_date`.
   - Compare worst rolling SL peaks against monthly peaks.
   - Rolling windows should become the main stability view; monthly reports remain a calendar distribution view.

4. Attribute SL trades before changing rules.
   - Classify each SL as fast/mid/late by `hold_bars`:
     - `FAST_SL`: <=2 bars, likely entry/confirmation quality.
     - `MID_SL`: 3-5 bars, likely ordinary structure failure.
     - `LATE_SL`: >=6 bars, likely protection/structure-expiry issue.
   - Do not use `hold_bars`, `exit_reason`, or MFE as entry gates; they are post-entry fields.

5. Only simulate executable gates with pre-entry fields.
   - Valid examples: `risk_pct`, `tp2_rr`, combo key, signal type, tier, market state, structure state, DNA mode.
   - Invalid examples for entry filtering: `hold_bars`, final `exit_reason`, realized PnL, MFE after entry.

6. Risk-width diagnostics matter.
   - In V102, `risk_pct<0.7` had materially higher SL than baseline; the durable lesson is to test risk-width buckets before touching signal definitions.
   - Candidate gates must be validated by full replay/backtest, not accepted from retrospective CSV filtering alone.

## Recommended Report Outputs

For any monthly instability investigation, produce:

- Monthly SL table with sample confidence labels.
- Rolling20 stability CSV/report.
- Rolling50 stability CSV/report.
- SL attribution CSV with one row per SL trade.
- Executable gate simulation CSV using only pre-entry fields.
- Final improvement report with: problem, evidence, proposed gate, success criteria, and explicit non-recommendations.

## Success Criteria for a Candidate Fix

A candidate filter should be promoted only if full replay/backtest shows:

- Lower global SL rate or lower rolling-window SL peak.
- Net WR not worse than the production baseline.
- Trade count remains acceptable for the production objective.
- No future-function or T+1 violation is introduced.
- Frontend/API fields remain synchronized if promoted.

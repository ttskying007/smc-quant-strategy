# V95 Exit Contract Post-Exit Autopsy Pattern

Use this reference when Lei asks whether TP/SL or runner exits are structurally wrong. The durable lesson is not the V95 numbers themselves; it is the exit-contract audit method.

## Trigger

Run this pattern when:
- V88/Vxx signal quality looks acceptable but realized profit capture is questionable.
- The user asks whether trades were sold too early or whether SL/TP placement is wrong.
- Exit buckets include many `RUNNER_TRAIL`, `TIME_STOP`, or `SL_HIT` rows.

## Required sequence

1. **Keep the signal layer fixed.** Do not change selection, SMC signal definitions, or entry logic while auditing exits.
2. **Run full trade population, not samples.** Use the production trade JSON and daily K-line cache for every row.
3. **Enforce T+1.** Exit replay starts from the first daily bar after `entry_date`; same-day buy/sell is a hard error.
4. **For every trade, inspect post-exit prices.** After `exit_date`, compute 3/5/10/20 trading-day:
   - max high return from exit price
   - min low return from exit price
   - close return
   - max high in R from original entry/risk
   - min low in R from original entry/risk
5. **Bucket by exit reason before proposing fixes:**
   - `RUNNER_TRAIL`: sold-early detection and dynamic runner trailing design
   - `TIME_STOP`: high-MFE capture / delayed runner logic
   - `SL_HIT`: protective SL vs washout/early-entry SL
6. **Build a shadow exit contract.** Create a new Vxx exit-only contract that leaves the signal layer untouched, then compare full-population baseline vs shadow.
7. **Report both aggregate and row-level evidence.** Provide CSV/JSON rows for per-trade review plus a phone-readable markdown table summary.

## Classification rules that worked in V95

For `SL_HIT` rows:

- `WASHOUT_SL_REBOUNDED_TO_2R`: post-exit 20-day max high reaches at least +2R from original entry. Treat as SL placement / washout candidate.
- `EARLY_ENTRY_THEN_WASHOUT_REBOUND`: post-exit 20-day max high reaches +2R but the same window also extends to roughly -2R or worse. Treat as entry-too-early / insufficient confirmation before treating as SL width.
- `PROTECTIVE_SL_CONTINUED_DOWN`: post-exit 20-day low continues below -1R and max high stays below entry. Treat as valid protective SL.
- `BORDERLINE_SL_RECLAIMED_ENTRY_NOT_2R`: price reclaims entry but does not reach +2R. Treat as confirmation/buffer review, not automatic SL widening.

For `TIME_STOP` rows:

- If MFE >= 1.5R, evaluate a capture rule such as `mfe_50pct_cap_3r`: capture `min(max(MFE * 0.5, 1.5R), 3R)` rather than simply holding longer.
- Distinguish high-MFE-not-captured from low-MFE-dead trades.

For `RUNNER_TRAIL` rows:

- Post-exit 20-day high continuation proves many runners are sold early, but simultaneous post-exit drawdown means the answer is **dynamic trailing**, not unlimited hold or global TP widening.
- Split the next iteration into trend-continuation vs spike-and-reversal runner buckets.

## V95 session outcome snapshot

V95 audited V88's 532 trades over 2023-05-17 to 2026-06-01 entries. It fixed no signal logic; it only simulated an exit contract.

Key findings:
- V88 baseline: 532 trades, WR 83.65%, avg +2.8689%, cum +1526.26%, SL 12.97%, TIME_STOP 11.09%, RUNNER 75.94%.
- V95 shadow exit: WR 86.09%, avg +2.9382%, cum +1563.10%, SL unchanged at 12.97%, TIME_STOP down to 4.70%, RUNNER up to 82.33%.
- `RUNNER_TRAIL` 404 rows: after exit, 20-day max high averaged +11.9155%; 70.54% rose >5%, 41.58% rose >10%, but 52.48% also later fell >5%.
- `TIME_STOP` 59 rows: V93-style MFE capture improved the bucket from WR 69.49% / avg +1.6975% to WR 91.53% / avg +3.6757%.
- `SL_HIT` 69 rows: only 12 looked like protective SL; 39 were washout/early-entry candidates; 18 were borderline reclaim rows.

## Pitfalls

- Do not answer TP/SL questions from aggregate WR/RR only.
- Do not widen all SL just because some stopped trades later rebounded.
- Do not lengthen all runner exits just because many sold trades continued upward; post-exit drawdown must be measured too.
- Do not mix signal-layer changes into an exit-contract audit. Create a shadow exit contract first.
- Do not claim completion without row-level output that includes post-exit 3/5/10/20-day fields.

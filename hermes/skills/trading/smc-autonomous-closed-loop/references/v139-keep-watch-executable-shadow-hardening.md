# V139 KEEP_WATCH executable shadow hardening lesson

Session context: continuing the V126+ read-only/shadow A-share SMC research stream after V138 produced executable simulations for KEEP_WATCH_STRONG rows.

## Boundary

- Read-only/shadow only: no production/API/frontend/watchlist/TP/SL writes.
- Input: `/root/.hermes/smc_audit/v138_keep_watch_strong_executable_semantic_audit_20260620/v138_executable_entry_exit_shadow_backtest.csv`.
- Output: `/root/.hermes/smc_audit/v139_keep_watch_strong_semantic_hardening_20260621/`.

## Reusable workflow

1. Start from executable simulation rows, not historical outcome labels alone.
2. Compare entry modes first:
   - `RECLAIM_NEXT_OPEN`
   - `T2_NEXT_OPEN`
   - `T3_NEXT_OPEN`
3. Pick the entry mode by executable PnL/MAE/MFE/T+1 behavior, not by a later confirmation story.
4. Run rule sensitivity on candidate gates one at a time before composing gates.
5. Reject over-hardening when a rule shrinks samples sharply without improving average PnL, recent coverage, or loss rate materially.
6. Decompose remaining losses by semantic exit reason before touching TP/SL.

## V139 finding to reuse

For KEEP_WATCH_STRONG executable rows, `RECLAIM_NEXT_OPEN` beat waiting for T2/T3. Waiting for more confirmation raised adverse excursion and reduced average PnL.

Best non-production shadow gate from this pass:

```text
RECLAIM_NEXT_OPEN + market_state != MIXED
```

Metrics from V139:

| slice | n | WR | Avg | Median | Loss | Recent n | Recent WR | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| RECLAIM_NEXT_OPEN all | 408 | 77.70% | +2.3875% | +2.9809% | 22.30% | 32 | 75.00% | 0 |
| RECLAIM_NEXT_OPEN + non-MIXED | 273 | 80.22% | +2.9981% | +3.7033% | 19.78% | 30 | 76.67% | 0 |
| Hardened combo | 21 | 80.95% | +2.6035% | +3.9807% | 19.05% | 2 | 100.00% | 0 |

Important interpretation: the hardened combo did not justify production or even preferred shadow status because it collapsed coverage and did not improve average PnL.

## Loss anatomy lesson

For the non-MIXED RECLAIM_NEXT_OPEN slice, remaining losses were mostly semantic failure, not exit-parameter failure:

| bucket | loss_n | loss_share_pct |
|---|---:|---:|
| risk>6 | 45 | 83.33% |
| ZONE_CLOSE_DEAD | 43 | 79.63% |
| entry_above_zone>2 | 28 | 51.85% |
| reclaim_bull_body<50 | 20 | 37.04% |
| reclaim_close_pos<60 | 12 | 22.22% |

Next research step should be a read-only K-line semantic replay of `ZONE_CLOSE_DEAD_T1` losers to find ex-ante failure precursors. Do not respond by tuning TP/SL.

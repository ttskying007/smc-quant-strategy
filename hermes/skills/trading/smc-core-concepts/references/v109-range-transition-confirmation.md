# V109 RANGE_TRANSITION Confirmation Semantic Rebuild

Use this reference when continuing SMC strategy-body research after V107C/V108, especially inside `BULL_EXPANSION` where `TREND_UP` works but `RANGE_TRANSITION` is noisy.

## Scope

- Research-only; do **not** connect to production/API/frontend from this evidence alone.
- Input baseline: V104 strict reclaim rows + V107C 750-bar full-market breadth regime classification.
- Target slice: `BULL_EXPANSION + RANGE_TRANSITION`.
- Do not tune TP/SL for this step; the question is confirmation semantics.
- Do not use `MIXED_CHOP` small samples for promotion.

## Core Lesson

`BULL_EXPANSION` is not one homogeneous regime:

| Slice | n | WR | SL | Avg |
|---|---:|---:|---:|---:|
| BULL_EXPANSION | 147 | 72.11% | 25.85% | 2.5167% |
| BULL TREND_UP | 60 | 86.67% | 13.33% | 4.2802% |
| BULL RANGE_TRANSITION | 87 | 62.07% | 34.48% | 1.3004% |

The strong component is `TREND_UP`; `RANGE_TRANSITION` requires stricter confirmation.

## V109 Confirmation Rule Tested

For `BULL_EXPANSION + RANGE_TRANSITION` only:

```text
ACCEPT research row only if:
  event_to_entry is 8..21
  OR a second post-event swing-high break is confirmed before entry

REJECT if:
  event_to_entry < 8 and no second structure confirmation exists
```

Result:

| Slice | n | WR | SL | Avg |
|---|---:|---:|---:|---:|
| V109 accepted research-only | 31 | 77.42% | 22.58% | 2.7601% |
| V109 accepted unique symbol-date | 24 | 75.00% | 25.00% | 2.4235% |
| V109 rejected | 56 | 53.57% | 41.07% | 0.4924% |
| Fast rejected 0-7 no second | 56 | 53.57% | 41.07% | 0.4924% |

Interpretation: delaying `RANGE_TRANSITION` confirmation helps, but the accepted set is still too small/unstable for production.

## Duplicate Family Pitfall

V109 exposed repeated same-symbol/same-entry-date rows caused by `REVERSAL` and `CONTINUATION` both firing:

| Slice | duplicate_groups | duplicate_rows |
|---|---:|---:|
| BULL RANGE_TRANSITION | 20 | 42 |
| V109 accepted | 7 | 14 |

Future production-style evaluation must report both raw row metrics and `unique(symbol, entry_date)` metrics. Do not promote based only on duplicated family rows.

## Monthly Stability Requirement

V109 accepted research-only covered only 7 months, with several tiny months (`n=1/2/4`). This fails production stability even though headline WR improved. Continue as research until a fresh full-market multi-year generator passes monthly gates.

## Next Research Direction

If continuing to V110, inspect accepted-loss rows rather than tuning exits:

1. `risk_pct > 5`: may indicate zone too wide / SL structure too far.
2. `retrace_pct > 40`: may indicate POI deep consumption before reclaim.
3. duplicate family: merge at generator layer before metrics.
4. `event_to_entry=8` boundary: test if 9..21 or second-confirm-only removes remaining SLs.

Keep production at V90 WATCH_ONLY / tradable active=0 unless a fresh full-market multi-year gate passes.

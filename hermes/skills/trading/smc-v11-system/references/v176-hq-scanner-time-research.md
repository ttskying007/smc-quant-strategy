# V176 HQ scanner-time research lesson

Use this when continuing SMC production research after a semantic-label repair or after a high-WR subset appears promising but is not yet production-sized.

## Context

After V175, the primary event label was corrected from overclaiming classical `SSL_SWEEP_CHOCH_REVERSAL` to the more honest `DEMAND_OB_TRUE_TAKEOVER_RECLAIM`. The economics were preserved but not a final quality jump:

- V175: n=247, WR=83.81%, Avg=6.0493%, SL=8.91%, min_year=38.
- This is a semantic-contract fix, not a complete production promotion.

## Required acceptance gates before claiming production

Define the result gate before searching rules:

- Production usable: n>=120, WR>=88%, Avg>=6%, SL<=8%, min_year_n>=20, every year WR>=80% and SL<=15%, T+1=0, scanner-time fields only.
- High-quality research candidate: n>=60, WR>=90%, Avg>=6%, SL<=7%, min_year_n>=8, no year WR<80% or SL>20%, scanner-time fields only.
- Unusable: fails the above, depends on outcome fields, or depends on historical enrichment that current scanner cannot compute.

## V176 result

No production-ready rule was found. Best high-quality research candidate:

```text
reclaim_close_pos <= 0.8363
AND entry_chase_above_zone_pct <= 2.6904
AND risk_pct <= 6
```

Historical result on V175 source rows:

| n | WR | Avg | SL |
|---:|---:|---:|---:|
| 67 | 94.03% | 6.0879% | 4.48% |

Year breakdown:

| Year | n | WR | SL |
|---|---:|---:|---:|
| 2023 | 12 | 100.0% | 0.0% |
| 2024 | 25 | 92.0% | 4.0% |
| 2025 | 21 | 90.48% | 9.52% |
| 2026 | 9 | 100.0% | 0.0% |

Current V175 active picks hit by this HQ rule: 6 of 26. Strict small-sample rule hit: 1 of 26.

## Workflow rule

Do **not** keep slicing the same 247 V175 rows after this point. That becomes overfit secondary filtering.

Next valid step is generator-level research:

1. Write the three scanner-time constraints into the generator/dry-run candidate layer.
2. Re-run full-market historical scanner-time generation, not just post-filter historical trades.
3. Verify no outcome-field leak and no historical-only field dependency.
4. Re-check annual stability, T+1, active pick source, API/front-end field contracts.
5. Only promote if the production gate passes; otherwise label as `HQ_RESEARCH_ONLY`.

## Interpretation

The durable signal is not “classical SSL sweep/CHOCH was validated.” The durable signal is:

- Demand OB true takeover works better when reclaim closes in the middle/upper-but-not-overextended part of the zone.
- Avoid chasing entries too far above the zone.
- Keep risk below 6%.

This should guide the next generator, not become a production label by itself.

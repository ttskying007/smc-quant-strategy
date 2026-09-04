# V76 Environment Persistence + SMC Story Machine

## Trigger

Use this when V74-style environment state improves SMC demand-zone trades but early recovery/reversal batches still fail, especially with POI close-break losses.

## Durable finding

V76 tested environment persistence + story-specific gates on the V75 annotated V74-selected set (850 trades). It improved signal quality but did **not** reach production readiness.

| Version | Trades | WR | Avg PnL | SL rate | POI break rate |
|---|---:|---:|---:|---:|---:|
| V74 baseline | 850 | 69.41% | +1.1645% | 30.59% | 26.24% |
| V76 strict gate | 203 | 72.91% | +1.3384% | 27.09% | 22.66% |

V76 strict gate failed by year:

| Year | Trades | WR | Avg PnL | POI break rate |
|---|---:|---:|---:|---:|
| 2023 | 15 | 66.67% | +1.3916% | 26.67% |
| 2024 | 13 | 23.08% | -2.9463% | 69.23% |
| 2025 | 132 | 81.06% | +1.9644% | 15.15% |
| 2026 | 43 | 65.12% | +0.6935% | 30.23% |

## Best searched gate

Best high-WR gate:

```text
prior_days=10
max_distribution_days=0
min_demand_days=2
max_bsl_distance_pct=2.0
max_bull_breadth=0.55
```

Result: 178 trades, WR 79.78%, avg +1.846%, POI break 17.98%.

But it has no 2024 coverage and only 24 trades in 2026, so it is not production-grade.

## New root cause

2024 failures show `RECOVERY` is too broad. In V74-selected 2024 trades:

| Bucket | Trades | WR | Avg PnL | POI break count |
|---|---:|---:|---:|---:|
| BULL_CONTINUATION | 31 | 74.19% | +1.7549% | 7 |
| RECOVERY | 28 | 32.14% | -1.9075% | 17 |
| ACCUMULATION | 12 | 91.67% | +3.4783% | 0 |

V76 strict gate admitted a bad RECOVERY reversal batch on 2024-03-18 / 2024-05-20: 13 trades, WR 23.08%, POI break 69.23%.

Therefore `RECOVERY + DOWN_REVERSAL_SSL_CHOCH` cannot directly authorize demand-zone entries. It must be split into:

- true accumulation recovery: prior stable accumulation/demand-valid breadth and improving structure;
- weak rebound / false recovery: MIXED-to-RECOVERY or low-quality recovery after weak structure, where demand POIs still fail.

## Next step

V77 should not tune TP/SL. It should add a recovery-quality sub-state:

1. Require RECOVERY setups to have prior accumulation/demand persistence, not just 2-3 RECOVERY days after MIXED.
2. Add stock-level relative strength / POI durability before allowing reversal setups.
3. Preserve continuation setups separately; UP_CONTINUATION in BULL_CONTINUATION remains the strongest story.
4. Validate on full V71/V74 annotated sets and keep production unchanged unless every year has sufficient coverage and WR.

## Files

- `/root/.hermes/scripts/v25/v76_env_persistence_story_machine.py`
- `/root/.hermes/smc_opt_v76_env_persistence_story_machine/v76_report.json`
- `/root/.hermes/smc_opt_v76_env_persistence_story_machine/v76_report.md`
- `/root/.hermes/smc_opt_v76_env_persistence_story_machine/v76_annotated_trades.json`

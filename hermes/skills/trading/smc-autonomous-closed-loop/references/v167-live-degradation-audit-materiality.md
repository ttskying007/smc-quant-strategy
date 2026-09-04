# V167 live degradation audit materiality

## Trigger
Use when running the post-close V167 live degradation audit:

```bash
cd /root/.hermes/scripts
python3 /root/.hermes/scripts/v25/v170_v167_live_degradation_audit.py
```

Primary artifact:

```text
/root/.hermes/smc_audit/v170_v167_live_degradation_audit_20260623/summary.json
```

## Materiality rule
A material report is required if any condition is true:

- `overall.sl_hit_pct >= 20`
- `live_tradable != active_pick_count`
- any API/script error
- any new concentrated bucket has `n >= 3` and `sl_hit_pct >= 50`

## Important interpretation
`live_tradable != active_pick_count` is a material reporting condition, but not automatically a price-degradation or strategy-failure signal.

When this mismatch fires, separate the conclusion into two layers:

1. **Material condition:** report the mismatch numerically, e.g. `live_tradable=4 / active_pick_count=33`.
2. **Risk diagnosis:** check whether this is accompanied by actual degradation:
   - `sl_hit_pct`
   - number of `sl_hit_rows`
   - number of `tp_hit_rows`
   - concentrated buckets with high SL rate
   - API/script errors

If SL rows are zero and there is no concentrated loss bucket, state clearly that the audit is material because of tradability/context mismatch, but not a price-degradation event. Do not mutate production or add gates from this audit alone.

## Output pattern
For user-facing reports, keep it concise and tabular:

```markdown
| 项 | 结果 |
|---|---:|
| active_pick_count | 33 |
| live_tradable | 4 |
| SL_HIT | 0 |
| TP_HIT | 0 |
| avg_live_pnl_pct | +0.007% |

结论：触发 material condition：`live_tradable != active_pick_count`。但不是价格退化型风险：SL_HIT=0、无集中亏损桶、脚本无错误。继续 live-forward monitoring，暂不调整生产。
```

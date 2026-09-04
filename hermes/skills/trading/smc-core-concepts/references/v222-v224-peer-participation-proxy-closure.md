# V222-V224 peer participation proxy research closure

Date: 2026-06-27

## Trigger
Use after V221 when considering the remaining valid post-V185 direction: a non-leaking sector/peer participation layer. Local repo has no explicit industry/sector map, so V222 used a conservative proxy from all cached daily K-lines: global/board/prefix-2/prefix-3 peer breadth and position metrics from the **previous market day only**.

## Artifacts
- V222 peer participation probe: `/root/.hermes/smc_audit/v222_peer_participation_proxy_probe_20260627_030356/`
- V223 independent rule audit: `/root/.hermes/smc_audit/v223_peer_participation_rule_audit_no_write_20260627_030703/`
- V224 current active smoke: `/root/.hermes/smc_audit/v224_v223_current_active_rule_smoke_20260627_0308.json`
- Temporary scripts: `/tmp/v222_peer_participation_probe.py`, `/tmp/v223_peer_participation_independent_audit.py`

## No-leak contract
- Features are derived from local `kline_cache/*_daily_750.json` only.
- Selector date is `prev_market_date < entry_date`; V223 verified `time_order_bad_count=0`.
- Selector fields: `v185_source`, `v222_p3_up1_pct`, `v222_prev_market_date`, `v222_p3`.
- V223 selector leak fields: `[]`.
- No production/frontend/watchlist writes.

## V222 discovery result
V222 loaded 4,655 K-line files and tested 7,105 scalar/pair peer participation rules.

Baseline V185:
| n | WR | AvgPnL | minYear | yearWRmin | micro | T+1 |
|---:|---:|---:|---:|---:|---:|---:|
| 334 | 86.23% | 6.5628% | 41 | 82.81% | 0.90% | 0 |

Loss diagnostics showed losers tend to occur when the peer/market prefix group is weaker over 3-5 days but also has more one-day overheated breadth (`p3_strong1_pct` / `p3_up1_pct`).

Best research rule after exact threshold audit:
```text
keep all V185_CHILD;
keep V175_BASELINE only when previous-day prefix-3 peer up1 breadth <= 92.9594
```

## V223 audited metrics
| set | n | WR | AvgPnL | minYear | yearWRmin | micro | loss_n | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V185 baseline | 334 | 86.23% | 6.5628% | 41 | 82.81% | 0.90% | 46 | 0 |
| V223 selected | 312 | 88.46% | 6.8441% | 38 | 84.48% | 0.96% | 36 | 0 |
| V223 excluded | 22 | 54.55% | 2.5724% | 2 | 33.33% | 0.00% | 10 | 0 |

Delta vs baseline:
- WR +2.23pp
- Avg +0.2813pp
- yearWRmin +1.67pp
- loss count 46 → 36

Decision: `V223_RESEARCH_GATE_PASS__PRODUCTION_GATE_FAIL_MIN_YEAR__NO_WRITE`.

## Why not production
V223 passes research gate but fails the post-V185 production gate because `min_year_n=38 < 40`. It is a real non-leaking peer-participation signal, but not enough for immediate production routing.

Do not mutate frontend/watchlist/API from V223 alone.

## V224 current active smoke
Current V185 active rows: 6.
All 6 pass the V223 peer rule:
- 300327.SZ 20260616 p3=300 prev p3_up1=78.3784
- 688048.SH 20260616 p3=688 prev p3_up1=76.2808
- 688486.SH 20260616 p3=688 prev p3_up1=76.2808
- 002401.SZ 20260615 p3=002 prev p3_up1=73.9183
- 688277.SH 20260615 p3=688 prev p3_up1=60.3416
- 002937.SZ 20260610 p3=002 prev p3_up1=62.5899

Operational meaning: V223 would not remove any current active V185 row. It is a future risk guard for overheated prefix-3 peer breadth, not a current active-pick change.

## Next direction
Close local peer-proxy scalar filtering as production-upgrade path. Remaining valid directions:
1. obtain a real industry/sector mapping or sector index history, then rerun participation using true sector membership rather than prefix proxy;
2. build a new candidate generator using pre-entry intraday semantics, not filtering V185 rows;
3. if no new data layer is available, focus on V185 production stabilization/live guard/cron rather than endless scalar research.

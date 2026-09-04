# V343 BSL Room Production Gate Lesson (2026-07-09)

## Trigger
Use when an SMC branch has high WR but cannot meet production average PnL at full coverage after TP/SL/runner exit sweeps.

## Root cause found
V338-V342 showed exit architecture alone is insufficient. Fixed TP1+runner, OB zone width, and dynamic BSL target exits all failed or only passed on under-covered samples. The missing signal-layer condition was **pre-entry upside liquidity room plus lower-half position**.

## Production-passing rule (shadow-only verified)
Seed:
- `v164_rule_pass == true`
- industry gate: exclude weak industries unless breadth override passes
- `v132_bull_count_3 >= 3`
- `poi_source in {DEMAND_OB, OB+FVG, FVG_Demand}`

Pre-entry structural features, computed only from bars before `entry_date`:
- `bsl60_room_pct = (prior_60bar_high / entry_price - 1) * 100 >= 10`
- `pos60_pct = (entry_price - prior_60bar_low) / (prior_60bar_high - prior_60bar_low) * 100 <= 50`

Execution contract:
- T+1 only: path excludes entry date
- `sl = zone_low * 0.99`; if `sl >= entry`, use `entry * 0.985`
- TP1 = +4%, sell 30%
- runner = 70%, stop moves to BE after TP1
- TP2 = +60%, max_hold = 50 bars
- conservative same-bar policy: if same post-entry bar hits TP1 and low crosses BE, runner exits BE on that bar

## Verified results
V343 formal no-write:
- all rows: 767; hist eligible: 744; current rows: 12; current open: 2
- metrics: n=744, WR=95.8333%, Avg=+7.7639%, micro=0%, min_year_n=93, min_year_WR=93.55%, T+1=0
- year WR: 2023 93.55%, 2024 96.02%, 2025 95.65%, 2026 98.06%

V344 dedup robustness:
- duplicate symbol/date groups: 82; extra duplicate rows: 115
- after symbol+entry_date dedup (non-outcome policies), n=629, WR=95.7075%, Avg=+8.2343%, min_year_n=73, min_year_WR=91.78%, T+1=0
- policies passing: best_poi_then_bsl, max_bsl, min_risk, prefer_ob

V345 cost stress:
- dedup policies survive cost haircut up to 0.2% per trade
- at 0.3%+, micro rate explodes because many BE-runner wins become <1%; do not claim robust beyond 0.2% cost under current micro gate

Artifacts:
- `/root/.hermes/smc_audit/v343_bsl_room_deep_runner_latest.json`
- `/root/.hermes/smc_audit/v344_v343_dedup_robustness_latest.json`
- `/root/.hermes/smc_audit/v345_v343_cost_stress_latest.json`

## Caveats / promotion gate
Do not promote from V343 formal alone. Require V344 dedup pass and V345 cost stress pass. Current status is shadow-ready, not production-written.

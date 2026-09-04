# V71/V72 Smart Money Position Repair Lesson

Use this reference when an SMC engine shows high `ZONE_DEAD` after FVG-demand or OB-reaction repairs.

## What was tested

After V68/V70 showed that FVG zone-mid entries were not true smart-money positions, two structural repairs were tested full-market:

| Version | Core change | Full-market result | Decision |
|---|---|---:|---|
| V71 | Replace FVG solo zone with OB / OB-FVG overlap + discount/OTE + reaction + next-open entry | 9,931 trades, WR 55.15%, avg +0.1437%, SL 44.78% | Fail, no production |
| V72 | Anchor OB at SSL sweep-origin / pre-sweep bearish candle instead of displacement-before OB | 33,808 trades, WR 53.01%, avg +0.0076%, SL 46.96% | Worse, no production |

Both passed hard audits:
- T+1: 0 failures
- Semantic order: 0 failures
- Required frontend fields: 0 missing
- No FVG standalone entry in V71/V72

## Durable root cause

Changing the zone label from FVG to OB is insufficient. In full-market A-share daily data, many OB/reaction setups still die immediately:

V71 SL autopsy:

| SL feature | Value |
|---|---:|
| SL count | 4,447 |
| Exit close below zone | 3,794 = 85.3% |
| Zone failed in 1-3 bars | 2,697 = 60.6% |
| MFE < 0.25R before SL | 2,681 = 60.3% |
| MFE >= 0.8R before SL | 259 = 5.8% |

Interpretation: most losses are not missed trailing exits. The zone never produced meaningful favorable excursion.

## What NOT to do next

- Do not keep widening SL: close-below-zone dominates.
- Do not use micro TP to fake WR: V71 RR0.05 reached only 79.1% WR and negative expectancy.
- Do not promote a recent-year-only filter: 2025/2026 improves, but this is a regime dependency and not a complete production standard.
- Do not assume sweep-origin OB is better: V72 was worse than V71.

## Key evidence

V71 by year:

| Year | n | WR | avg | SL |
|---|---:|---:|---:|---:|
| 2023 | 1,901 | 46.45% | -0.5353% | 53.50% |
| 2024 | 2,701 | 45.80% | -0.6502% | 54.20% |
| 2025 | 4,336 | 63.42% | +0.8504% | 36.46% |
| 2026 | 986 | 60.95% | +0.5077% | 38.95% |

V72 by year was similarly regime-dependent and worse overall.

## Next valid direction

The next repair must be above the single-stock POI layer:

1. Add a non-leaking market-structure environment gate, not generic MA/RSI.
2. Market gate should be structural breadth / index-like SMC state, e.g. percentage of universe with active HH/HL, recent bullish CHOCH continuation, or broad-market liquidity-to-demand confirmation.
3. Keep V71 OB/reaction semantics as the cleaner base; discard V72 sweep-origin OB as primary.
4. Re-run full-market replay and release only if robust across 2023/2024/2025/2026, not just recent years.

## V73 environment-layer validation

V73 tested exactly this next layer by annotating V71 trades with non-leaking full-universe structural breadth and per-stock confirmed swing state.

| Gate | n | WR | avg | SL | Decision |
|---|---:|---:|---:|---:|---|
| V71 base | 9,931 | 55.15% | +0.1437% | 44.78% | insufficient |
| Market env only | 4,455 | 60.70% | +0.5541% | 39.26% | useful but insufficient |
| Env + stock trend | 3,574 | 62.51% | +0.6734% | 37.49% | useful but insufficient |
| Full context quality | 1,514 | 63.74% | +0.7724% | 36.26% | not production |

Critical finding: environment breadth is necessary but still incomplete. 2023 remained bad under the full gate (270 trades, WR 47.04%, avg -0.5313%). In 2023, `BULL_ENV` was actually worse (WR 38.6%, avg -1.13%) while `RECOVERY_ENV` worked (WR 66.7%, avg +0.86%). Therefore bullish breadth alone can label a distribution/overextended regime as demand-valid.

Next engine must add an environment state machine, not just a breadth threshold:

- `ACCUMULATION / RECOVERY / BULL_CONTINUATION / DISTRIBUTION / BEAR_RISK`
- split continuation and reversal stories explicitly:
  - `UP_CONTINUATION -> BOS -> HL pullback -> POI reclaim`
  - `DOWN/COMPRESSION -> SSL sweep -> CHOCH/MSS -> POI reclaim`
- add invalidation based on POI break, prior HL break, and environment transition to distribution.

V73 files:
- `/root/.hermes/scripts/v25/v73_structural_environment_gate_search.py`
- `/root/.hermes/smc_opt_v73_structural_env/v73_gate_report.json`
- `/root/.hermes/smc_opt_v73_structural_env/v73_structural_env_report.md`

## V74 environment state machine validation

V74 implemented the next valid direction as a non-leaking environment state machine plus separate setup stories.

| Version / Gate | n | WR | avg | SL | Decision |
|---|---:|---:|---:|---:|---|
| V71 base | 9,931 | 55.15% | +0.1437% | 44.78% | insufficient |
| V73 full context | 1,514 | 63.74% | +0.7724% | 36.26% | useful but 2023 failed |
| V74 env state machine core gate | 850 | 69.41% | +1.1645% | 30.59% | direction correct, not production |

V74 states:
- `ACCUMULATION / RECOVERY / BULL_CONTINUATION` are demand-valid states.
- `DISTRIBUTION / BEAR_RISK / MIXED` reject demand zones.
- A high-breadth rally can still be `DISTRIBUTION` when it is a violent breadth squeeze with range expansion; this fixed much of 2023's false `BULL_ENV` problem.

V74 story split:
- `UP_CONTINUATION_BOS_POI_RECLAIM`: stock uptrend + Bull BOS + valid POI + reclaim.
- `DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM`: recovery/accumulation environment + Bull CHOCH + valid POI + reclaim.
- FVG solo remains banned as a demand zone.

V74 improved 2023 from negative to marginal positive but still did not meet production criteria:

| Year | n | WR | avg | SL |
|---|---:|---:|---:|---:|
| 2023 | 102 | 56.86% | +0.2659% | 43.14% |
| 2024 | 71 | 60.56% | +0.6019% | 39.44% |
| 2025 | 514 | 73.93% | +1.4976% | 26.07% |
| 2026 | 162 | 66.67% | +0.9101% | 33.33% |

Next valid direction: keep V74 as signal-layer base and diagnose remaining 2023/2024 losses by post-entry structural invalidation: close below POI, prior HL break, failed recovery, BSL target availability, and environment transition exit. Do not promote V74 to production yet.

## V75 post-entry invalidation audit

V75 audited V74 selected trades bar-by-bar after entry. The main remaining loss mechanism is not TP/SL distance; it is POI death after entry:

| Primary label | Count | Meaning |
|---|---:|---|
| `LOSS_POI_CLOSE_BREAK_BEFORE_TP` | 223 | Price closed below demand POI before reaching target. |
| `LOSS_TP_OVERSHOOTS_NEAREST_BSL` | 17 | TP target sits beyond nearest buy-side liquidity, reducing hit probability. |
| `LOSS_ENV_RISK_BEFORE_TP` + `LOSS_ENV_WEAK_BEFORE_TP` | 12 | Broad environment deteriorated before target. |

Naive early exit on POI close-break reduced average loss but also cut winners; it is not a standalone solution. The stronger discovery was environment-state hysteresis: isolated one-day `BULL_CONTINUATION` flips after several `DISTRIBUTION` days are dangerous. On V74, adding `prior5_distribution_days == 0` improved the full gate to 535 trades, WR 73.08%, avg +1.4049%, but 2024/2026 still need more work.

Best research sub-gate found so far:

| Gate | n | WR | avg | SL | Notes |
|---|---:|---:|---:|---:|---|
| `BULL_CONTINUATION` + `market_bull_breadth <= 0.50` + nearest BSL distance <= 2% + `prior5_distribution_days == 0` | 65 | 89.23% | +2.6170% | 10.77% | High quality but too few trades and no 2023/2024 coverage; research-only. |

V75 files:
- `/root/.hermes/scripts/v25/v75_post_entry_invalidation_audit.py`
- `/root/.hermes/smc_opt_v75_post_entry_invalidation/v75_report.json`
- `/root/.hermes/smc_opt_v75_post_entry_invalidation/v75_annotated_trades.json`
- `/root/.hermes/smc_opt_v75_post_entry_invalidation/v75_gate_candidate.json`
- `/root/.hermes/smc_opt_v75_post_entry_invalidation/v75_hysteresis_probe.json`

## V76 environment hysteresis + risk-environment exit

V76 implemented the V75 finding as executable rules on top of V74's selected setup layer:

1. Entry hysteresis: reject if any of the prior 5 market sessions were `DISTRIBUTION`.
2. Risk cap: reject setups with `risk_pct > 5.2` because the remaining large-risk bucket concentrated POI-death losses.
3. Post-entry environment exit: after T+1, exit on the first close where broad environment becomes `DISTRIBUTION` or `BEAR_RISK`.

Validation on the V74 selected 850-trade set:

| Gate / exit | n | WR | avg | SL | Notes |
|---|---:|---:|---:|---:|---|
| V74 selected actual exit | 850 | 69.41% | +1.1645% | 30.59% | baseline |
| V76 entry gate, original exit | 412 | 73.79% | +1.4036% | 26.21% | distribution-hysteresis removes fake bull flips |
| V76 entry gate + env risk exit | 412 | 72.33% | +1.4213% | 15.05% | lower WR but better payoff and much lower SL |

V76 env-exit by year:

| Year | n | WR | avg | SL |
|---|---:|---:|---:|---:|
| 2023 | 63 | 71.43% | +1.2829% | 23.81% |
| 2024 | 23 | 73.91% | +1.2512% | 4.35% |
| 2025 | 258 | 73.26% | +1.6097% | 10.47% |
| 2026 | 67 | 68.66% | +0.8638% | 28.36% |

Audit: 0 T+1 violations, 0 missing exit fields. Decision: V76 is the first layer to make 2023/2024/2025/2026 all positive, but it is still validated only as a filter over V74's 850 selected trades. Do not promote directly; next step is to push V76 hysteresis/env-exit into the full V71/V74 candidate generation layer and rerun full-market scanning so coverage is not overfit to a selected subset.

V76 files:
- `/root/.hermes/scripts/v25/v76_environment_hysteresis_engine.py`
- `/root/.hermes/scripts/v25/test_v76_environment_hysteresis.py`
- `/root/.hermes/smc_opt_v76_environment_hysteresis/v76_report.json`
- `/root/.hermes/smc_opt_v76_environment_hysteresis/v76_report.md`
- `/root/.hermes/smc_opt_v76_environment_hysteresis/v76_simulated_trades.json`

## V77/V78 recovery quality and trend hygiene

See `references/v77-v78-recovery-quality-trend-hygiene.md` for the follow-on lesson. Short version: splitting `RECOVERY` into demand-valid vs false recovery and adding trend/target hygiene can reduce SL materially, but V78 only had 106 selected trades and 2024 had only 2 trades on the V74/V75 candidate layer. Therefore V77/V78 remain research gates until pushed into the full 4900+ stock candidate generator. Do not promote thin high-WR yearly coverage.

V74 files:
- `/root/.hermes/scripts/v25/v74_environment_state_machine.py`
- `/root/.hermes/scripts/v25/test_v74_environment_state_machine.py`
- `/root/.hermes/smc_opt_v74_env_state_machine/v74_report.json`
- `/root/.hermes/smc_opt_v74_env_state_machine/v74_report.md`
- `/root/.hermes/smc_opt_v74_env_state_machine/v74_annotated_trades.json`
- `/root/.hermes/smc_opt_v74_env_state_machine/v74_selected_trades.json`
- `/root/.hermes/smc_opt_v74_env_state_machine/v74_env_by_date.json`

## Files from discovery

- `/root/.hermes/scripts/v25/v71_smart_money_position_engine.py`
- `/root/.hermes/smc_opt_v71_smart_money_position/v71_report.json`
- `/root/.hermes/smc_opt_v71_smart_money_position/v71_zone_dead_autopsy.json`
- `/root/.hermes/scripts/v25/v72_sweep_origin_ob_engine.py`
- `/root/.hermes/smc_opt_v72_sweep_origin_ob/v72_report.json`

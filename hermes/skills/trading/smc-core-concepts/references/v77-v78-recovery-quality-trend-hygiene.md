# V77/V78 Recovery Quality + Trend Hygiene Lessons

Use this reference when a high-WR SMC candidate layer improves recent years but still has weak yearly coverage, or when RECOVERY/BULL_CONTINUATION batches fail after POI reclaim.

## What changed

V77 split the broad `RECOVERY` state into demand-valid vs false/unproven recovery using only pre-entry facts:

- `TRUE_RECOVERY_DEMAND_VALID`: clean demand-valid prior environment plus intact stock structure/POI.
- `FALSE_RECOVERY_AFTER_WEAK_OR_DISTRIBUTION`: recent weak/distribution history; high POI-death risk.
- `MIXED_RECOVERY_UNPROVEN`: not safe enough for production even if aggregate WR looks acceptable.

V78 added trend/target hygiene on top of V74/V75/V77:

- V74 core story remains mandatory: Context → Event → POI → Reclaim.
- Reject recent Distribution contamination.
- Reject overheated market breadth squeezes (`market_bull_breadth > 0.50`).
- Require prior demand-valid environment (`prior10_demand_valid_days >= 3`).
- Reject too much prior distribution (`prior5_distribution_days == 0`, `prior10_distribution_days <= 3`).
- Require stock-level HL improvement before entry.
- Reject `STRUCTURE_LOW_RISK` pseudo-discount zones; they were frequently shallow/late pullbacks rather than true smart-money locations.
- Use T+1-safe environment exit on later `DISTRIBUTION` / `BEAR_RISK`.

## Validation result on V74/V75 candidate layer

| Version | n | WR | avg | SL | Env exit | Decision |
|---|---:|---:|---:|---:|---:|---|
| V77 gate | 474 | 71.73% | +1.2095% | 28.27% | 0% | Improves 2024 but still not production |
| V78 original exit | 106 | 78.30% | +1.6868% | 21.70% | 0% | Too narrow |
| V78 env exit | 106 | 72.64% | +1.7660% | 7.55% | 26.42% | Strong but coverage too small |

V78 environment-exit by year:

| Year | n | WR | avg | SL | Env exit | cum |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | 24 | 87.50% | +2.1124% | 8.33% | 4.17% | +50.70% |
| 2024 | 2 | 100.00% | +4.2016% | 0.00% | 0.00% | +8.40% |
| 2025 | 70 | 65.71% | +1.5137% | 8.57% | 35.71% | +105.96% |
| 2026 | 10 | 80.00% | +2.2132% | 0.00% | 20.00% | +22.13% |

T+1 audit: 0 violations.

## Durable decision

Do **not** promote V77/V78 directly from the selected V74/V75 candidate subset. V78 is a candidate gate, not production, because:

- total selected trades fell to 106;
- 2024 has only 2 trades;
- the validation is still over a pre-filtered 850-trade V74 subset, not the full 4900+ stock candidate generator.

## Next valid workflow

1. Push V78 rules into the full V71/V74 candidate generation layer, not a post-hoc subset filter.
2. Re-run full-market scan across 4900+ stocks.
3. Require per-year coverage before promotion; high WR with thin yearly coverage is not sufficient.
4. Keep environment exit T+1-safe: no exit on entry date; only evaluate `DISTRIBUTION` / `BEAR_RISK` from T+1 onward.
5. If yearly coverage collapses, loosen only rules that were proven not structural, and preserve the signal-correctness gates: V74 core story, POI intactness, recovery-quality split, and T+1 exit discipline.

## Key files from the session

- `/root/.hermes/scripts/v25/v77_recovery_quality_state_machine.py`
- `/root/.hermes/scripts/v25/v78_hysteresis_recovery_trend_gate.py`
- `/root/.hermes/smc_opt_v77_recovery_quality_state_machine/v77_report.md`
- `/root/.hermes/smc_opt_v78_hysteresis_recovery_trend_gate/v78_report.md`

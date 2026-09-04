# V469–V472 industry-lead → stock-lag SSL transmission closure

Use this reference when continuing local, pure-structure cross-security SMC research after same-day market/industry SMT divergence has failed.

## Distinct frozen ontology

`ex-stock industry composite raids confirmed 3L/3R SSL and closes back above it → industry closes above raid-bar high within 3 sessions → target stock raids its own independently verified SSL during the next 10 sessions while the industry still holds above the swept SSL → stock reversal confirms → next-session open`

This is temporal liquidity transmission, not the closed same-day SMT-divergence ontology. The target stock is excluded from its geometric-mean industry composite; at least 15 peers are required.

## Pre-outcome evidence

- Full-market no-outcome generator: 32,559 seeds.
- Yearly support: 2023=3,296; 2024=10,208; 2025=13,929; 2026=5,126.
- Semantic-order failures=0; duplicate symbol/entry identities=0; forbidden outcome headers=0.
- Independent raw-bar oracle reproduced 32,559/32,559 seeds with mismatch=0.
- Important multi-series audit rule: never compare bar indices across stock and composite series. Validate cross-series chronology using trading dates; indices are meaningful only within one series.

## Single frozen strict-T+1 replay

Execution was frozen before outcomes:

- entry: next open after stock reversal confirmation;
- SL: stock raid low × 0.99;
- target: nearest pre-entry-confirmed stock 3L/3R BSL;
- exit: target/SL/time20, strict T+1, gap-aware, same-bar collision=SL;
- fee=0.2%; search count=1.

| Scope | n | Gross WR | Net WR >=0.8% | AvgNet | Payoff | PF | SL |
|---|---:|---:|---:|---:|---:|---:|---:|
| Overall | 31,830 | 71.3478% | 50.4398% | +0.7101% | 0.6446 | 1.3640 | 25.6362% |
| 2023 | 3,295 | 61.5781% | 44.9165% | -0.6668% | 0.4790 | 0.7068 | 34.2033% |
| 2024 | 10,204 | 65.7781% | 55.5174% | +1.9629% | 0.9623 | 1.7354 | 28.8906% |
| 2025 | 13,918 | 76.6346% | 48.9151% | +0.2951% | 0.4732 | 1.2068 | 21.7057% |
| 2026 | 4,413 | 74.8470% | 47.6320% | +0.1503% | 0.4665 | 1.0885 | 24.1106% |

Versus unconditioned Turtle Soup: AvgNet +0.5124pp, payoff +0.1095, PF +0.2633, SL -1.5741pp. Versus same-day industry SMT: AvgNet +0.8308pp, payoff +0.1953, PF +0.4289.

## Decision

The ontology contains real aggregate information and is materially better than same-day industry divergence, but it fails all-year stability: 2023 expectancy/PF are negative and 2026 PF is below the frozen 1.15 gate. Close it without lag-window, SL, TP, hold, pivot, or peer-count variants. Do not promote to production, frontend, watchlist, or shadow.

## Metric-audit pitfall

Do not classify stop exits using substring checks such as `'SL' in exit_reason`: valid target reasons like `KNOWN_BSL_TP_T1` contain the letters `SL` inside `BSL`, producing a false 100% SL rate. Use an explicit stop-reason set, for example:

- `STRUCTURAL_RAID_SL_T1`
- `SL_GAP_T1`
- `SL_TP_COLLISION_CONSERVATIVE_T1`

Independent summary generation is not complete until recomputed metrics match the frozen replay field-by-field after this classification check.

Artifacts: `v469_industry_lead_stock_lag_latest.json`, `v470_industry_lead_stock_lag_oracle_latest.json`, `v471_industry_lead_stock_lag_frozen_t1_replay_latest.json`, `v472_industry_lead_stock_lag_closure_latest.json`.

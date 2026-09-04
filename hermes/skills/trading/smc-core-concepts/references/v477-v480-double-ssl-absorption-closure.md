# V477–V480 double-SSL absorption reversal closure

Use after the single-raid Turtle Soup and internal-inducement branches are closed.

## Frozen ontology

`most-recent confirmed 3L/3R SSL → first >=0.3% wick raid/close-back without closing above its raid high → 2..10 bars later a higher-low second raid of the same SSL/close-back while the first raid floor remains intact → close above both raid highs within 3 bars → next-session open`.

This is distinct from single-raid Turtle Soup because the first raid must remain unresolved and a second higher-low absorption test must occur before expansion. It is distinct from internal inducement continuation because it starts from an external SSL and requires no prior bull BOS.

## Integrity and support

- Full market symbols: 4,903.
- Semantic seeds: 24,236; years 2023/24/25/26 = 3,185 / 8,051 / 8,830 / 4,163.
- Independent raw-bar oracle: 24,236/24,236, mismatch 0.
- Semantic chronology failures: 0.
- Replay chronology failures: 0.
- T+1 violations: 0.
- Search count: 1.

## Frozen replay

Execution: next open; SL at deepest raid low × 0.99; target nearest pre-entry confirmed 3L/3R BSL; max hold 20; fee 0.2%; gap-aware and same-bar collision conservatively assigned to SL.

| Scope | n | Gross WR | Net WR >=0.8% | AvgNet | AvgWin | AvgLoss | Payoff | PF | SL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| All | 23,531 | 74.08% | 51.66% | +0.2180% | +3.1844% | -6.8089% | 0.4677 | 1.1078 | 23.38% |
| 2023 | 3,184 | 64.48% | 47.71% | -0.4266% | +3.2994% | -6.5051% | 0.5072 | 0.8275 | 31.50% |
| 2024 | 8,049 | 69.28% | 55.04% | +0.2842% | +4.1913% | -7.7982% | 0.5375 | 1.1118 | 28.03% |
| 2025 | 8,824 | 81.04% | 51.43% | +0.4508% | +2.4882% | -5.9245% | 0.4200 | 1.3142 | 16.86% |
| 2026 | 3,474 | 76.31% | 48.04% | +0.0639% | +2.7637% | -6.4769% | 0.4267 | 1.0338 | 21.70% |

Independent metric recomputation matched all aggregate and yearly fields exactly.

## Decision

The second raid raises gross WR by 3.41pp versus single-raid Turtle Soup, but AvgNet improves only 0.0203pp, payoff worsens by 0.0674, PF improves only 0.0071, and 2023 remains negative. The architecture still produces frequent small wins and losses more than twice as large.

Close `DOUBLE_SSL_RAID_ABSORPTION_REVERSAL`. Do not reopen through raid spacing, depth, SL, TP, hold, year, or market-state variants.

Artifacts: `v477_double_ssl_absorption_latest.json`, `v478_double_ssl_absorption_oracle_latest.json`, `v479_double_ssl_absorption_frozen_t1_replay_latest.json`, `v480_double_ssl_absorption_direction_closure_latest.json`.

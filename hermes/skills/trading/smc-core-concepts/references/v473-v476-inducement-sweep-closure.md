# V473–V476 bullish internal inducement-sweep closure

Use when continuing local pure-structure SMC research after V472.

## Frozen ontology

`external protected low → confirmed swing high → bullish close-BOS → higher internal low → internal-low wick raid/close-back while external low remains untouched → close above raid high within 3 bars → next-session open`

This is distinct from generic Turtle Soup because it raids internal inducement liquidity inside an already-established bullish protected structure. It is distinct from Protected-Swing Transfer because it does not require a second BOS and POI retest.

## Evidence

- V473 outcome-blind full-market generator: 4,903 symbols, 6,223 unique seeds; yearly 2023/24/25/26 = 532/1,542/2,944/1,204; semantic-order failures 0.
- V474 independent raw-bar Oracle: 6,223/6,223 PASS, mismatch 0, forbidden outcome headers 0.
- V475 one frozen strict-T+1 replay: 6,066 closed trades, T+1 violations 0, search count 1.
- V476 independent metric recomputation: all aggregate/yearly metrics matched, mismatch fields 0.

## Frozen replay result

| Scope | n | Gross WR | AvgNet | Payoff | PF | SL |
|---|---:|---:|---:|---:|---:|---:|
| Overall | 6,066 | 74.40% | +0.0744% | 0.4436 | 1.0414 | 23.62% |
| 2023 | 531 | 64.78% | -0.6554% | 0.4101 | 0.6679 | 31.07% |
| 2024 | 1,540 | 66.43% | -0.3674% | 0.4842 | 0.8641 | 31.95% |
| 2025 | 2,937 | 79.71% | +0.4400% | 0.4647 | 1.3360 | 18.45% |
| 2026 | 1,058 | 76.09% | +0.0690% | 0.4095 | 1.0396 | 22.12% |

Average win +2.6690%, average loss -6.0168%. The high headline WR is offset by losses more than twice wins. 2023 and 2024 are negative.

## Decision

`INTERNAL_INDUCEMENT_SWEEP_HAS_HIGH_HEADLINE_WR_BUT_FAILS_PAYOFF_AND_ALL_YEAR_EXPECTANCY__CLOSE_NO_VARIANTS`

Do not rescue with risk bands, altered raid depth, SL/TP, hold period, year filters, or weekly/industry overlays. A future direction must change the causal ontology.

Artifacts: `v473_inducement_sweep_continuation_latest.json`, `v474_inducement_sweep_oracle_latest.json`, `v475_inducement_sweep_frozen_t1_replay_latest.json`, `v476_inducement_sweep_direction_closure_latest.json`.

# V415–V422 strict daily pure-structure closure

## Trigger
Use this reference before resuming a local-daily SMC “liquidity sweep → CHOCH/BOS → POI → retrace/reclaim” branch. It prevents treating a label-level lifecycle as a valid signal definition or re-running failed signals with different windows, thresholds, exits, or risk settings.

## Fixed usefulness gate
For a production claim, **every** 2023–2026 year must satisfy:

| Gate | Requirement |
|---|---:|
| Samples/year | >=40 |
| Positive 5D/10D mark rate | >=50% |
| Average mark | >=0% |
| Close-below-zone rate | <=30% |
| Execution | strict T+1 = 0 violations |

Small aggregate pockets cannot replace each-year support. Do not tune after outcome review.

## Semantic integrity invariant
A POI lifecycle must start after all prerequisites:

`event_idx/poi_idx → first post-prerequisite touch → reclaim → hold/takeover → next-session open`

For OB:
- The OB must be fresh: no wick mitigation or close invalidation between its source and the prerequisite event.
- A pre-event wick cannot be called a post-confirmation retest.

For FVG:
- The FVG source/creation bar cannot be labelled its own post-creation retest.

Always independently audit that lifecycle tuple order and that each T+1 replay row maps to one takeover seed.

## V415–V419 correction
V415 found that V409/V411 had semantic defects: pre-event OB mitigation and source-bar FVG lifecycle artifacts. V416 rebuilt strict semantic candidates.

V417 then ran the only allowed fixed replay: `TAKEOVER_CONFIRMED → next session open`, marks at 5/10/20 sessions, no TP/SL/threshold/exit search. V419 independently verified 21,042 rows: all chronology/T+1 checks pass and no outcome fields existed in seed inputs.

The corrected R1/R2/C1 results all failed the annual gate:

| Branch | 5D sample | 5D positive | 5D mean | Key failure |
|---|---:|---:|---:|---|
| R1 SSL→CHOCH→fresh OB | 172 | 40.12% | -0.5516% | negative and 10D zone invalidation 37.79% |
| R2 SSL→CHOCH→post-creation FVG | 653 | 36.29% | -0.7734% | negative and 10D zone invalidation 44.60% |
| C1 BOS→fresh OB | 20,172 | 44.45% | +0.1452% | low positive rate and 10D zone invalidation 34.79% |

They are economically closed. Do **not** reopen via scalar, wait-window, risk, TP/SL, or exit mining.

## V420–V421 R3 EQL-pool reversal
A qualitatively tighter R3 generator was tested:

`two confirmed equal lows within 0.3% → SSL sweep → bull CHOCH within 1..20 bars → fresh event-anchored demand OB → first touch/reclaim/hold → next-session open`

An independent audit caught a lifecycle tuple-field mapping bug before acceptance. The generator was corrected and rerun over all 4,655 symbols. Corrected result: only 55 candidates / 11 takeover seeds. V421 replay mapped all 11 source seeds to 11 T+1 entries with zero chronology failures.

| Horizon | n | Positive | Mean | Zone invalidated |
|---|---:|---:|---:|---:|
| 5D | 11 | 45.45% | -1.1692% | 9.09% |
| 10D | 11 | 45.45% | -0.7353% | 36.36% |
| 20D | 11 | 27.27% | +3.5760% | 72.73% |

R3 is both too sparse to ever reach the fixed support gate and negative at the usable 5D/10D horizons. Close it; do not relax equal-low tolerance or timing after seeing this result.

## Decision
Local daily pure-structure R1/R2/C1/R3 frontier is closed. A future local-data direction is allowed only if it is a **qualitatively distinct, predeclared causal generator**, passes all-universe semantic/lifecycle/chronology audit before outcomes, and has >=160 takeover seeds distributed as >=40 per year. Otherwise stop rather than iterate.

Artifacts: `v415_poi_lifecycle_integrity_latest.json`, `v416_strict_semantic_combination_rebuild_latest.json`, `v417_strict_semantic_frozen_t1_replay_latest.json`, `v419_strict_semantic_replay_integrity_latest.json`, `v420_eql_pool_reversal_latest.json`, `v421_eql_pool_reversal_frozen_t1_replay_latest.json`, `v422_pure_structure_closure_latest.json`.

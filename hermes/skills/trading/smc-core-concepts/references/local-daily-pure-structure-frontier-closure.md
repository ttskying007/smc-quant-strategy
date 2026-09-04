# Local Daily Pure-Structure Research Frontier Closure

Use this reference when a user requests continuing SMC research after extensive local daily-OHLCV testing, or asks whether another backtest/parameter iteration is justified.

## Core rule

Do not treat a structurally distinct signal definition as proven tradable merely because its sequence is causal. Separate:

1. **semantic correctness** — every event, POI, touch, reclaim, and takeover can be re-derived from only then-visible bars;
2. **execution correctness** — next-session entry and T+1 are enforced;
3. **economic usefulness** — stable positive fixed-horizon behavior across every year.

A failure at (3) closes that ontology. It does not justify threshold, window, entry, TP/SL, or holding-period mining.

## Frozen admission and usefulness gates

Before opening outcomes for a new ontology:

- State why it is qualitatively different from already closed ontologies.
- Run a full-universe, no-outcome semantic/lifecycle/chronology audit.
- Enforce one execution identity per symbol per takeover day.
- Require at least 160 takeover seeds, with at least 40 in each of 2023–2026.

For the one allowed frozen T+1 diagnostic:

- Entry: next trading-session open after `TAKEOVER_CONFIRMED`.
- No TP/SL, exit, threshold, or horizon selection during the replay.
- Every year must meet: `n >= 40`, positive fixed-horizon marks `>= 50%`, average mark `>= 0`, POI/zone invalidation `<= 30%`, and T+1 violations `= 0`.
- Aggregate performance or a single strong year never substitutes for yearly stability.

## Closed local-daily pure-SMC ontologies

The following all passed causal construction/integrity where applicable but failed the frozen economic gate; do **not** reopen them with parameter variants:

| ID | Causal ontology | Closure evidence |
|---|---|---|
| R1 | SSL sweep → bull CHOCH → fresh demand OB → first touch/reclaim/hold | 5D n=172, positive 40.12%, avg -0.5516%; 10D invalidation 37.79% |
| R2 | SSL sweep → bull CHOCH → post-creation bull FVG → first touch/reclaim/hold | 5D n=653, positive 36.29%, avg -0.7734%; 10D invalidation 44.60% |
| C1 | bull BOS → fresh demand OB → first touch/reclaim/hold | 5D n=20,172, positive 44.45%, avg +0.1452%; 10D invalidation 34.79% |
| R3 | EQL pool → SSL → CHOCH → fresh demand OB → lifecycle | only 11 takeovers; support fails before quality, and marks negative |
| R4 | two-sided balance → SSL reclaim → range-high BOS → fresh breaker → lifecycle | 5D n=2,022, positive 49.06%, avg +0.4850%; 10D invalidation 31.25%; weak 2023/2024/2026 periods |
| R5 | PO3 accumulation → SSL manipulation → bull distribution → fresh breaker → lifecycle | 5D n=395, positive 46.84%, avg -0.2477%; 10D avg -0.2188%, invalidation 34.18% |

## Required response when this frontier is closed

- Explicitly say strategy research on the current local daily-OHLCV information set is complete.
- Stop instead of inventing another replay or claiming a parameter tweak is a new discovery.
- Keep only operational monitoring: data freshness, semantic drift, scanner provenance, and frontend/API/K-line consistency. These are not strategy improvements.
- A restart requires a genuinely distinct, predeclared causal ontology or a new admissible information source; it must repeat the full no-outcome audit before one frozen replay.

## Implementation evidence (2026-07-13)

- V419 independently verified 21,042 strict replay rows: zero chronology and zero T+1 failures.
- V424 independently re-derived R4: 4,642/4,642 pass.
- V428 independently re-derived R5: 985/985 pass.
- V431 registry audit: all R1–R5 closed, zero unclosed defined local-daily ontologies.

## V515–V516 final local-OHLCV frontier closure (2026-07-15)

A final genuinely distinct cross-timeframe ontology was frozen before outcomes:

`confirmed weekly range high/low -> weekly BSL raid/close-back -> 2..12 weeks later weekly SSL raid/close-back with no intervening close outside range -> post-week daily CHOCH -> post-purge daily Demand OB -> touch/reclaim/hold -> next-open eligibility`.

V515 scanned 4,897 symbols and found 2,803 weekly purge events, but only 51 complete semantic seeds, distributed 2023/24/25/26 as 6/10/19/16. Semantic-order failures and duplicate identities were zero, and no outcome fields were present. It failed the frozen pre-outcome floor (`n>=300`, every year `>=40`), so no replay or outcome inspection was allowed. Do not loosen weekly raid spacing, CHOCH window, OB lookback, or lifecycle rules after seeing scarcity.

V516 then audited the remaining verified frontier. No ontology passed all-year promotion. The highest gross WR was Internal Inducement Sweep (74.3983%) but payoff was 0.4436 and AvgNet only 0.0744%; the highest AvgNet/payoff was Weekly SSL Rejection Block (AvgNet 0.5351%, payoff 0.9479) but 2023 and 2026 were negative. Daily, cross-security, weekly POI/event, IFVG, breaker, and final weekly two-sided families are therefore closed on the current local OHLCV information set.

Decision: `CURRENT_LOCAL_OHLCV_PURE_STRUCTURE_RESEARCH_COMPLETE__ZERO_ALL_YEAR_PROMOTION_PASS__STOP_STRATEGY_ITERATION`. Only operational monitoring remains until a genuinely new causal ontology—not a timeframe/context/threshold/entry/exit variant—can be named and passes the same no-outcome support gate.

Artifacts: `v515_weekly_two_sided_purge_daily_transfer_latest.json`, `v516_local_structure_frontier_closure_latest.json`.

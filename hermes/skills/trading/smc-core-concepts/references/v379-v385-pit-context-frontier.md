# V379–V385 Raw-Source PIT Context Frontier

## Trigger

Use when daily/60min SMC research has passed causal signal audits but still has poor realized quality, and the next proposed fix is market breadth, sector leadership, relative strength, or peer confirmation.

## Non-negotiable research sequence

1. **Freeze the base execution contract first.** Retain source, entry, exit, T+1, de-duplication, and serial-position rules. Do not mix a context test with a new POI or TP/SL rule.
2. **Build a PIT data gate before reading outcomes.** For each candidate, materialize only features whose cutoff is at or before the completed confirmation bar (`hold_time`); entry must be the next bar's open.
3. **Check full coverage, not just success samples.** Require every candidate event time to have an accounted snapshot and a minimum valid cross-section/peer count. Quarantine source anomalies rather than imputing them.
4. **Predeclare discrete states before outcome replay.** Report every state; do not select thresholds after seeing PnL.
5. **Use a discovery gate before candidate-level rebuild.** Require adequate n and year coverage plus material uplift in WR, PnL, and worst-year WR. A modest aggregate gain is not a production signal.
6. **Only if the discovery gate passes, rerun at candidate level with serial execution.** Bucketed historical trades are diagnostic evidence only; filtering can alter which previously blocked candidates become executable.

## Raw data contract validated

- Daily OHLCV must be reconstructed only from exactly four valid 60min source slots (`10:30`, `11:30`, `14:00`, `15:00`).
- Any non-four-slot date is quarantined; detector segments reset after the gap.
- Legacy adjusted daily data may serve only as a calendar cross-check, never as price/POI/outcome input.
- Independently re-derive pivots, BOS/CHOCH, OB, FVG, and sweep logic and require zero differential mismatch before MTF replay.

## Findings: do not reuse these as production gates

### Whole-market equal-weighted participation

At completed `hold_time`, derive market up-rate versus prior close, median/P80 return, and intraday up-rate. All features must precede the next-60min-open entry.

On the V381 raw-daily POI → 60min reaction replay (n=4,832):

| State | n | WR | Avg PnL | SL |
|---|---:|---:|---:|---:|
| Baseline | 4,832 | 35.39% | -0.1562% | 56.91% |
| Broad risk-on | 1,539 | 39.64% | +0.4192% | 51.01% |
| Broad mixed | 1,691 | 33.47% | -0.4643% | 58.72% |
| Broad risk-off | 1,602 | 33.33% | -0.3837% | 60.67% |

Risk-on had a directional uplift but not enough to pass a predeclared discovery bar (WR uplift >=5pp, Avg PnL uplift >=1pp, worst-year WR uplift >=3pp). It is a weak diagnostic ranker, not a candidate-level or production rule.

### PIT behavior cohort confirmation

Avoid static/current industry labels. Build a cohort for each candidate from the 20 highest positive raw-daily return correlations over the preceding **20 completed sessions**. At `hold_time`, inspect only those peers' intraday returns from that day's open to the completed hold bar.

| State | n | WR | Avg PnL | SL |
|---|---:|---:|---:|---:|
| Baseline | 4,832 | 35.39% | -0.1562% | 56.91% |
| Cohort confirms | 2,401 | 37.78% | +0.1341% | 52.77% |
| Cohort mixed | 714 | 34.31% | -0.4658% | 59.38% |
| Cohort rejects | 1,717 | 32.50% | -0.4333% | 61.68% |

The confirmation bucket did not improve the 2023 worst-year result and failed the same predeclared discovery gate. Close this branch; do not mine correlation, peer count, or threshold variants.

## Durable conclusion

When raw-source SMC structure, reaction confirmation, whole-market participation, and behavior-cohort confirmation all fail their frozen discovery gates, **stop searching price-derived or price-cohort scalar filters**. The next class of research must bring a truly independent, point-in-time source with original publication timestamps: disclosures, earnings notices, institutional/dragon-tiger flow, verifiable historical fund-flow, or event metadata.

Before such a source is used, build its PIT availability gate: publication time <= event/entry decision time, multi-year coverage, no current-label backfill, and explicit quarantine for missing or ambiguous timestamps.

## V386–V390 PIT disclosure frontier (2026-07-12)

Eastmoney announcement metadata is technically usable as a PIT source: V386 queried all 4,832 frozen V381 decision rows across 788 hold dates; all 788 calls succeeded and every provider `eiTime` parsed. V387 then froze a title taxonomy before outcomes: regulatory/negative, capital-return/increase, fundamental-positive, business-positive, other, and no recent disclosure.

### Mandatory cache-scope invariant

V387/V388 were invalidated before promotion: their global per-symbol cache applied only `eiTime <= hold_time` and omitted the five-day lower bound. This let earlier announcement windows leak into later candidates for the same stock. A telltale symptom was a 2024 row classified from a 2023 timestamp. **Never use V388 metrics.**

V389 repaired the source contract without changing taxonomy: an announcement is eligible only when
`hold_time - 5 days <= eiTime <= hold_time`.

The repaired V390 replay stayed outcome-blind until feature data was frozen, then applied the same discovery bar:

| State | n | WR | Avg PnL | Result |
|---|---:|---:|---:|---|
| Baseline | 4,832 | 35.39% | -0.1562% | — |
| Fundamental-positive | 257 | 47.47% | +1.2354% | Directional effect, but **not eligible**: n<300 and min-year n=29<40 |
| Capital return/increase | 237 | 35.87% | -0.1447% | fail |
| Regulatory/negative | 233 | 34.33% | -0.5090% | fail |
| Business-positive | 68 | 36.76% | -0.2454% | fail |
| Other/no-disclosure | 4,037 | <=35.73% | <=-0.1056% | fail |

**Closure:** do not promote or widen the fundamental title bucket, extend the lookback, tune keywords, or run a candidate-level replay from the 257-row effect. Those actions would convert an underpowered diagnostic into fitting. The title-level disclosure branch is closed under the fixed gate. A future independent-event study must add new PIT information content, such as parsed announcement surprise/magnitude with original publication timestamp, not more title-token mining.

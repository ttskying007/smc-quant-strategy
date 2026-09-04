# V71 Anti-Live-SL Gate Lesson

Use this reference when a high-WR SMC candidate performs worse in live/monitor because many live entries hit SL despite good historical WR/RR.

## Trigger

Apply this workflow when:

- A version already has strong backtest metrics, but live positions are frequently stopped out.
- Loss-bucket audit shows `ENTRY_ABOVE_ZONE_HIGH`, `SL_NOT_BELOW_ZONE_LOW`, or `GAP_THROUGH_SL`.
- The user asks to preserve the successful runner/exit mechanism but harden live execution.

## Core Lesson

Do not respond to live SL concentration by simply widening SL or continuing to filter historical trades by outcome. Convert the live failure modes into pre-entry execution-contract gates.

The effective V71 pattern was:

| Failure Mode | Pre-entry Gate |
|---|---|
| `ENTRY_ABOVE_ZONE_HIGH` | Reject when entry price is too far above `raw_zone_high` |
| `SL_NOT_BELOW_ZONE_LOW` | Require SL to sit below `raw_zone_low` with a real buffer |
| `GAP_THROUGH_SL` | Reject T+1 next-open gap/execution deterioration risk |
| Oversized live risk | Reject high `risk_pct` before it becomes a monitor position |

## V71 Reference Thresholds

These were validated as an isolated candidate on V66 trades:

```python
MIN_SL_BELOW_ZONE_PCT = 1.0
MAX_ENTRY_ABOVE_ZONE_HIGH_PCT = 0.8
MAX_RISK_PCT = 6.0
MAX_NEXT_OPEN_GAP_DOWN_PCT = 2.5
```

Results in that run:

| Candidate | N | WR | SL Rate | Realized RR |
|---|---:|---:|---:|---:|
| V66 baseline | 137 | 90.51% | 8.76% | 6.307 |
| V71 anti-live-SL gate | 62 | 98.39% | 0.00% | 15.215 |

The important result was not just aggregate improvement: all historical `SL_HIT` and `GAP_SL_HIT` rows were rejected, and the remaining single loss was `TIMEOUT_STRUCTURAL`, not SL.

## Required Workflow

1. Keep the prior production version untouched; create an isolated candidate directory.
2. Replay the prior trade file and compute live-execution diagnostics from pre-entry fields only:
   - `entry_price` vs `raw_zone_high`
   - `sl` vs `raw_zone_low`
   - `risk_pct`
   - T+1 entry/open gap condition from cached K-line bars
3. Write `vXX_gate_reasons` and `vXX_live_sl_diag` into every kept/rejected row.
4. Prove the gate removed the actual loss bucket:
   - Count rejected `SL_HIT` and `GAP_SL_HIT` rows.
   - Verify kept trades have `SL_rate < 10%`.
   - Verify T+1 has no same-day exit/buy violations.
5. Slice the kept set by setup family, zone type, confirmation type, and year. Do not promote a gate that only works in one hidden bucket.
6. Only after backtest + bucket audit passes, wire the candidate into frontend/monitor as a selectable version; do not overwrite production immediately.

## Pitfalls

- Do not explain live SL away as “sample pollution” if the user is asking for a strategy hardening step. Sample hygiene matters, but the candidate still needs execution-contract gates.
- Do not widen SL to fix `SL_NOT_BELOW_ZONE_LOW`; require structurally valid SL placement below the zone.
- Do not use outcome fields inside the gate. Outcome fields are only for auditing whether the gate removed the intended historical failure bucket.
- Do not claim the signal semantics are fixed. V71 hardens live execution on top of a successful V66 runner/exit mechanism; semantic signal rebuilding remains a separate task.

## Reporting Pattern

Report compactly in tables:

- Baseline vs candidate metrics: N, WR, SL rate, Avg PnL, RR.
- Failure modes and their gates.
- Historical SL/GAP_SL removed vs remaining.
- Setup/zone/confirmation/year bucket checks.
- File paths for script, trades, rejected rows, picks, report.

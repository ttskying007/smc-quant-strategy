# V86 POI Width Production Gate Lesson

Session date: 2026-06-13

## Trigger

Use after V85 MIXED_ACCUMULATION production when the user asks for full repair, backtest, check, analysis, postmortem, or per-trade problem discovery.

## Root cause from V85 loss autopsy

V85 production had 559 rows / 89.09% WR / +2.7117% avg, but 61 losses remained.

Loss diagnosis:

| Diagnosis | n | avg loss | Meaning |
|---|---:|---:|---|
| EARLY_POI_CLOSE_BREAK_WITHIN_3BARS | 35 | -2.2998% | POI failed almost immediately after entry |
| RECOVERY_POI_CLOSE_BREAK | 17 | -2.4014% | RECOVERY state has weak POI support |
| TREND_DAMAGE_AFTER_ENTRY | 5 | -3.9778% | structure broke after entry |
| RECOVERY_TREND_DAMAGE_WEAK_ENV | 4 | -3.0490% | RECOVERY trend takeover failed |

Main root cause: residual losses are dominated by POI close-break, not T+1, frontend fields, or TP/SL formula.

The cleanest actionable contamination bucket was wide POI:

| Bucket | n | WR | avg | POI break | trend damage |
|---|---:|---:|---:|---:|---:|
| keep zone_width<=1.6 | 532 | 89.85% | +2.6845% | 8.65% | 1.69% |
| reject zone_width>1.6 | 27 | 74.07% | +3.2484% | 22.22% | 3.70% |
| V85 base | 559 | 89.09% | +2.7117% | 9.30% | 1.79% |

Do not hard-reject all RECOVERY yet: it improves quality but drops total below 500. RECOVERY needs a future substate rebuild, not a blunt production cut.

## V86 production rule

Source: `/root/.hermes/smc_opt_v85_production_gate/v85_trades.json`

Gate:

```text
1 < zone_width_pct <= 1.6
1 < risk_pct <= 1.5
hold_bars <= 2
takeover = HOLD_ABOVE_POI
T+1 enforced
```

Files:

- `/root/.hermes/scripts/v25/v86_production_gate.py`
- `/root/.hermes/scripts/v25/test_v86_production_gate.py`
- `/root/.hermes/scripts/v25/v86_loss_autopsy.py`
- `/root/.hermes/smc_opt_v86_production_gate/v86_trades.json`
- `/root/.hermes/smc_opt_v86_production_gate/v86_picks.json`
- `/root/.hermes/smc_opt_v86_production_gate/v86_production_report.json`
- `/root/.hermes/smc_opt_v86_production_gate/v86_report.md`
- `/root/.hermes/smc_opt_v86_production_gate/v86_trade_log_full.csv`
- `/root/.hermes/smc_opt_v86_production_gate/v86_losses_only.csv`

## Result

| Layer | n | WR | avg | POI break | trend damage | TP rate | cum |
|---|---:|---:|---:|---:|---:|---:|---:|
| V85 production | 559 | 89.09% | +2.7117% | 9.30% | 1.79% | 88.91% | +1515.85% |
| V86 production | 532 | 89.85% | +2.6845% | 8.65% | 1.69% | 89.66% | +1428.15% |

By year:

| Year | n | WR | avg | POI break | trend damage |
|---|---:|---:|---:|---:|---:|
| 2023 | 108 | 87.04% | +2.2286% | 10.19% | 3.70% |
| 2024 | 123 | 89.43% | +2.5123% | 9.76% | 0.81% |
| 2025 | 223 | 91.03% | +2.8895% | 7.62% | 1.35% |
| 2026 | 78 | 91.03% | +3.0010% | 7.69% | 1.28% |

Production criteria passed:

- total >= 500
- each year 2023–2026 >= 50
- each year 2023–2026 WR >= 65%
- T+1 violations = 0
- field audit = 0 missing

## Frontend sync

`smc_unified.py` was updated to prefer V86 when `/root/.hermes/smc_opt_v86_production_gate/v86_production_report.json` exists:

- `ACTIVE_VERSION = V86`
- `ACTIVE_TRADE_FILE = /root/.hermes/smc_opt_v86_production_gate/v86_trades.json`
- `ACTIVE_PICK_FILE = /root/.hermes/smc_opt_v86_production_gate/v86_picks.json`

Additional V86 compatibility fixes:

- `get_version_trades('V86')`
- `get_version_picks('V86')`
- current scoped version includes V86
- `_normalize_pick_scope` treats V86 as active-scoped
- `get_active_picks` returns V86 ACTIVE_CANDIDATE rows
- `normalize_v27_trades` does not cut V86 backtest rows by a rolling three-year cutoff; V86 file itself is already the curated 2023–2026 production universe.

Verified:

- `/api/picks`: 532 rows, engine V86, zero missing select/pick date, join date, zone, cost, volatility.
- `/api/summary`: total_trades 532, win_rate 89.8, avg_pnl 2.68.
- `/api/picks/contract`: active_pick_count 532.

Caveat: `/api/live-prices` still contains rows from legacy monitor ledger/daily monitor state. That is a monitor-state sync problem, not a V86 backtest/API-picks problem.

## Next direction

Do not make another global gate cut unless it preserves total >=500 and yearly coverage.

Next work should target:

1. RECOVERY substate rebuild: distinguish strong recovery reclaim from weak bounce.
2. V86 remaining 54 losses: per-trade second-pass autopsy by same mechanism.
3. Reversal path rebuild remains separate: SSL sweep → CHOCH → reclaim hold → subsequent HH/HL.
4. Monitor ledger migration: switch live monitor state away from stale V66 rows.

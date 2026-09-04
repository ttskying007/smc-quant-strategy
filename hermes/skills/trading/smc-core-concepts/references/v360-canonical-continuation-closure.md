# V360 Canonical Daily Continuation Closure

Use after V351–V359 when evaluating daily BOS→backward-OB continuation research.

## Non-negotiable cohort identity

A valid daily continuation replay must use one physical OB zone only:

1. semantic causal bull BOS and backward nearest bearish OB;
2. retain only the **earliest BOS** attached to that `(symbol, ob_idx, zone_low, zone_high)`;
3. reject the zone if its wick had touched `zone_high` before that BOS (`PRE_EVENT_MITIGATED`);
4. reject it if a pre-BOS close was below `zone_low` (`PRE_EVENT_INVALIDATED`);
5. after BOS: first wick touch → close reclaim above zone → a next hold above zone;
6. require two extra closes above `zone_high`; only then model next-open entry;
7. no exit may inspect entry-day H/L/C (A-share T+1).

Do not use V358's `unique` label as proof of this identity: V358 reads V354 identity rows, not V357 canonical physical-OB rows.

## V360 result — closed branch

V360 corrected the cohort and replayed only V357 canonical fresh persistent takeovers:

| Measure | Result |
|---|---:|
| canonical input paths | 53,164 |
| persistent takeovers | 14,055 |
| closed T+1 replays | 13,761 |
| WR | 69.38% |
| Avg PnL | +0.2872% |
| 2023 WR / Avg | 51.91% / -1.6935% |
| 2024 WR / Avg | 68.69% / -0.0456% |
| 2025 WR / Avg | 73.44% / +0.5250% |
| 2026 WR / Avg | 68.00% / +1.1961% |
| T+1 violations | 0 |

It fails the fixed promotion thresholds (`n>=300`, each 2023–2026 year `>=40`, WR `>=87%`, AvgPnL `>=6.8%`, worst-year WR `>=84%`, T+1 `=0`). **Do not promote it.**

The only valid next strategy research input is full auditable 60min history from 2023 onward; current local cache begins around 2025-10 and cannot establish historical promotion evidence. Do not resume daily OHLC scalar filtering or exit-grid mining.

Artifacts:
- `/root/.hermes/scripts/v25/v360_canonical_persistent_takeover_daily_t1_replay.py`
- `/root/.hermes/smc_audit/v360_canonical_persistent_takeover_daily_t1_replay_latest.json`
- `/root/.hermes/smc_audit/v360_research_closure_20260712.md`

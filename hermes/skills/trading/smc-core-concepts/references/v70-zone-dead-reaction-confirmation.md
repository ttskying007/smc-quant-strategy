# V70 Zone-Dead / Reaction Confirmation Lesson

Use this reference when an SMC L→D / FVG demand strategy has high SL rate, low WR, or the user points out that `zone_dead` dominates losses. This captures the durable workflow and mechanism discovered in the V68→V70 iteration.

## Core finding

A high `ZONE_DEAD` SL rate means the signal design is wrong, not merely that SL/TP needs tuning.

Observed on V68 full-market replay:

| Metric | Value |
|---|---:|
| Trades | 5,546 |
| WR | 58.17% |
| SL trades | 2,310 |
| `ZONE_DEAD_CLOSE_BELOW_LOW` among SL | 2,241 / 2,310 = 97.0% |
| `STRUCTURE_BROKEN` among SL | 1,746 |
| Immediate zone failure | 1,365 |

Interpretation: price returned to FVG and the strategy entered at/near zone midpoint before demand proved it could react. The zone was often already failing; SL was a symptom.

## Required diagnostic sequence

When the user asks why there are many SLs, do **not** start with parameter optimization. Run a full root-cause audit over every SL trade:

1. **Zone validity**
   - Did the SL bar close below `zone_low`?
   - Did it also break the latest pre-entry swing low?
   - Did the zone fail within 1–3 bars after entry?
2. **Entry timing**
   - `confirm_bar -> entry_bar` too small = entered before reaction confirmation.
   - Too large = stale zone / late chase.
   - Entry position inside zone: entry too high in zone or touch too deep.
3. **Trend context**
   - Trend down / 60-bar downtrend should be separated from range/up contexts.
   - Extended-up chase is also a distinct failure mode.
4. **TP/SL geometry**
   - MFE before SL in R multiples: if many trades reached 0.5R+ then failed, TP/trailing is part of the issue.
   - If zone closed below low, wider SL does not solve correctness; it hides invalid demand.
5. **Recovery after SL**
   - If later hit TP after wick stop, classify as SL too tight.
   - If close-through + structure break, classify as signal/zone invalid.

Root labels used in V70 audit:

- `ZONE_FAILED_IMMEDIATELY`
- `TREND_WRONG`
- `ENTRY_TOO_EARLY_AFTER_CONFIRM`
- `ENTRY_TOO_LATE_STALE`
- `ENTRY_TOO_HIGH_IN_ZONE`
- `TP_TOO_FAR_OR_NO_TRAIL`
- `SL_TOO_TIGHT_RECOVERED`
- `GAP_SL`, `WICK_SL`, `CLOSE_SL`

## Mechanism repair pattern

For FVG demand L→D systems, do not treat a touch of the FVG as sufficient. Require post-touch reaction confirmation:

```text
SSL_SWEEP
→ BULL_DISPLACEMENT
→ FVG_DEMAND
→ TOUCH_ZONE
→ REACTION_CONFIRMATION
→ NEXT_OPEN_ENTRY
→ STRUCTURE_SL
→ TP
```

Reaction confirmation variants tested:

| Variant | Meaning |
|---|---|
| `reclaim_zone_high` | after touch, close back above FVG high with bullish body |
| `two_bar_reclaim` | two-bar survival/reclaim after touch, then close above zone high |
| `break_disp_high` | stronger continuation break above displacement high; low frequency |

Durable lesson: **waiting for reaction confirmation reduced zone-dead SLs far more than moving SL wider.**

## V70 candidate outcome

Full-market V70 reaction-confirm replay:

| Scope | n | WR | Avg PnL | SL rate | Audit |
|---|---:|---:|---:|---:|---|
| all reaction-confirm variants | 7,479 | 81.60% | +0.4799% | 18.38% | semantic/T+1/fields pass |
| high-precision `two_bar_reclaim + structure SL + RR0.10 + ret20>0` | 67 | 98.51% | +0.5821% | 1.49% | semantic/T+1/fields pass |

Year split for high-precision candidate:

| Year | n | WR | Avg PnL | SL rate |
|---|---:|---:|---:|---:|
| 2023 | 14 | 100.00% | +0.6562% | 0.00% |
| 2024 | 15 | 100.00% | +0.7530% | 0.00% |
| 2025 | 26 | 96.15% | +0.3854% | 3.85% |
| 2026 | 12 | 100.00% | +0.7083% | 0.00% |

Caveat: sample size 67 is high precision but low frequency. Do not replace production with it without a broader deployment decision; it can be a sub-engine or further research candidate.

## Promotion gate

Before any production/frontend sync:

- Full-market replay, not sample-only.
- T+1 strict: `exit_idx > entry_idx`.
- Semantic order strict:

```text
liq_bar < displacement_bar
zone_bar <= displacement_bar + 1
 displacement_bar < touch_idx <= reaction_confirm_idx < entry_idx
```

- Required fields non-empty: `symbol`, `entry_date`, `pick_date`, `join_date`, `zone_type`, `zone_low`, `zone_high`, `cost_line`, `smart_money_cost`, `volatility_pct`, `entry_price`, `sl`, `tp1`.
- Do not claim completion until trades, picks, API, live page, K-line markers, analysis/review pages are synced and verified.

## Reporting pattern for Lei

When the user challenges low WR or SL root cause, report compact tables only:

1. SL primary-root distribution.
2. Mechanism change vs old behavior.
3. Full-market metrics + audit gates.
4. Year/month split for any >90% candidate.
5. Explicit sync state: candidate only vs production synced.

Avoid framing a low-frequency 90% candidate as production-ready unless the full production closure is complete.

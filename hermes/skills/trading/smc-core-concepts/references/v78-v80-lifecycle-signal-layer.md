# V78/V79 Full-Candidate SMC Lifecycle Audit Lesson

Use this reference when SMC iterations show that changing FVG→OB, anchoring OB differently, or adding TP/SL gates still does not solve signal correctness.

## User correction captured

The core task is not field repair, T+1, TP/SL tuning, or simple OB anchoring. The signal layer must explicitly track the smart-money lifecycle:

1. **Trend regime first**: up continuation, down reversal required, range/accumulation, bear risk.
2. **Event second**: SSL sweep, CHOCH/MSS reversal, BOS/CHOCH/MSS continuation.
3. **POI third**: price must return to a real Demand POI created by the event, not a reused/renamed FVG midpoint.
4. **Entry location fourth**: distinguish wick retest, close reclaim, late chase, and failed reclaim.
5. **Exit/invalidity last**: distinguish POI close-break, prior HL/trend damage, BSL/TP hit, and normal retest.

Do not claim smart-money tracking from aggregate WR/RR alone. Mechanism validation must precede production promotion.

## Durable workflow

When existing candidates are suspected to be structurally wrong:

1. Write small lifecycle primitives and tests before another full backtest:
   - `classify_trend_regime()`
   - `detect_smc_lifecycle_event()`
   - `locate_demand_poi()`
   - `evaluate_entry_location()`
   - `classify_exit_semantics()`
2. Include tests for both stories:
   - uptrend continuation: `UP_CONTINUATION → BOS/MSS → Demand POI pullback → reclaim`
   - reversal: `DOWN/RANGE → SSL sweep → CHOCH/MSS → Demand POI pullback → reclaim`
3. Include invalidation tests:
   - wick pierce of POI is not invalidation
   - **close below POI** is invalidation
   - **close below prior HL** is trend damage even if POI still holds
   - BSL hit after the actual stop horizon must not relabel a loser as TP
4. Run the lifecycle audit on the **full candidate layer**, not only the already-filtered selected subset.
5. If full-candidate lifecycle filtering leaves early-year coverage too thin, do not keep tightening gates. Rebuild the candidate generator so lifecycle states generate candidates in the correct order.

## Session evidence

Full candidate audit over V71/V73 layer:

| Layer | n | WR | avg | SL | Decision |
|---|---:|---:|---:|---:|---|
| V71/V73 full candidates | 8,709 | 55.29% | +0.1410% | 44.63% | baseline insufficient |
| V78 lifecycle core valid | 211 | 78.20% | +1.7098% | 21.80% | mechanism improves but coverage fails |
| V79 stricter lifecycle gate | 59 | 72.88% resim | +1.1555% | 25.42% | too strict, no production |

V78 full-candidate selected by year:

| Year | n | WR | avg | SL | Decision |
|---|---:|---:|---:|---:|---|
| 2023 | 6 | 50.00% | -0.3738% | 50.00% | fail |
| 2024 | 3 | 33.33% | -1.7145% | 66.67% | fail |
| 2025 | 154 | 79.22% | +1.8446% | 20.78% | works |
| 2026 | 48 | 81.25% | +1.7518% | 18.75% | works |

V79 stricter gate by year:

| Year | n | WR | avg | SL | Decision |
|---|---:|---:|---:|---:|---|
| 2023 | 4 | 25.00% | -6.4531% | 50.00% | fail |
| 2024 | 1 | 100.00% | +2.1613% | 0.00% | too few |
| 2025 | 47 | 78.72% | +1.9407% | 21.28% | works |
| 2026 | 7 | 57.14% | +0.0876% | 42.86% | weak |

## Key conclusion

The lifecycle decomposition is directionally correct: it raises total quality sharply. But applying it as a filter to old V71/V73 candidates still fails 2023/2024 and coverage. This proves the old candidate generator is the limiting layer.

The next valid step is a **V80 candidate generator rebuild**, not more filtering:

1. For each stock/day, classify trend/environment first.
2. Generate candidates by story:
   - `UP_CONTINUATION → BOS/MSS → Demand POI → reclaim`
   - `DOWN/RANGE → SSL sweep → CHOCH/MSS → Demand POI → reclaim`
   - `RANGE_ACCUMULATION → range-low liquidity sweep → breaker/OB reclaim`
3. Do not reuse old V71 `zone_bar` as truth. Recompute event-derived POI.
4. Simulate exits with T+1 and lifecycle invalidation:
   - SL/POI close-break
   - prior HL break
   - nearest BSL/TP
   - broad environment risk exit
5. Only promote after full-market, all-year coverage and mechanism audit pass.

## Pitfalls

- Do not mistake `TAKE_PROFIT_BSL_HIT` from a scan beyond the actual exit horizon as proof a losing trade would have hit target. Bound exit semantic scans by `exit_idx` or simulated horizon.
- Do not treat `STRUCTURE_LOW_RISK` as automatically valid. In early-year failures it often represented ambiguous location rather than true Demand POI.
- Do not make reversal setups from already-up stock contexts. Reversal requires weak/down/range context plus bullish CHOCH/MSS after liquidity event.
- Do not keep adding gates when early-year samples collapse below production coverage; that is a generator problem.

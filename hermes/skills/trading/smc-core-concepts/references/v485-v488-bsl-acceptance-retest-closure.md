# V485–V488 External BSL Acceptance/Retest Closure

Use this when considering a bullish continuation based on a broken buy-side liquidity level flipping to support.

## Distinct ontology

`confirmed external BSL → close acceptance >=0.3% above → 2–10 bar first retest holds the broken BSL → close above retest high within 3 bars → next-open entry`

This is distinct from:
- C1 BOS→OB: it retests the broken liquidity level, not an order block.
- Turtle Soup: it requires close acceptance above BSL, not wick raid and close-back rejection.
- Target-First DOL: it requires acceptance, retest, and re-expansion before entry.

Frozen execution: SL at retest low ×0.99; target nearest higher BSL already visible before acceptance; strict T+1; 20-session timeout; 0.2% fee; one replay only.

## Full-market result

Artifacts: `v485_bsl_acceptance_retest_latest.json` through `v488_bsl_acceptance_retest_direction_closure_latest.json`.

- Symbols scanned: 4,903
- Semantic seeds: 62,567; all years supported
- Independent oracle: 62,567/62,567, zero mismatch
- Closed trades: 33,495
- Gross WR: 56.5756%
- Net >=0.8% WR: 47.1473%
- AvgNet: -0.0402%
- Payoff: 0.7909
- Profit factor: 0.9831
- SL: 41.7644%
- T+1 violations: 0
- 2023 AvgNet -0.6718%; 2024 -0.5342%; 2025 +0.4410%; 2026 -0.0242%
- 45.4776% of seeds had the known higher-BSL target already consumed by next-open execution.

## Durable conclusion

The ontology is causal and abundant but economically negative after fees and unstable across years. The dominant flaw is structural timing: acceptance→retest→re-expansion often consumes the next known BSL before a legal next-open entry. Do not reopen this lineage through threshold, wait-window, SL, TP, hold-period, or year filters. Any future continuation direction must change the target/entry ontology itself, not tune this branch.

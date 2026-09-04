# V192-V194 post-V175 research continuation closure

Date: 2026-06-25

## Trigger

Use when continuing SMC research after V175/V180-V191, especially if the user asks whether the prior tasks are complete and what direction can still produce a qualitative change.

## Fixed gates

Production upgrade usable:
- non-leaking source-side rule;
- T+1 violations = 0;
- combined engine `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API mutation before dry-run passes.

Research child engine usable:
- non-overlap vs V175;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

## New executions in this continuation

### V192 — limit-up / attention impulse → demand retest raw generator

Artifact: `/root/.hermes/smc_audit/v192_limitup_demand_retest_generator_20260625_153050`

Contract:
- raw daily K-line cache only;
- not a V128/V167 filter;
- attention impulse creates demand zone, later touch + separate reclaim, entry next open;
- T+1 enforced; shadow-only.

Best child:
- `n=3177`, `WR=33.46%`, `Avg=0.2884%`, `median=-3.6223%`;
- `min_year_n=191`, `all_year_WR_min=26.18%`;
- exits: `TP_LIQUIDITY_TARGET=1005`, `SL=1663`, `GAP_SL=409`, `TIME=100`;
- T+1 violations = 0.

Decision: `V192_NO_RESEARCH_CHILD_PASS__LIMITUP_DEMAND_RETEST_CLOSED`.

Root cause: post-limit-up demand retest is still mostly a falling-knife retest; the raw demand zone is not institutionally protected enough. A large impulse alone does not identify smart-money absorption.

### V193 — FVG_Demand high-WR micro bucket runner replay

Artifact: `/root/.hermes/smc_audit/v193_fvg_attention_runner_replay_20260625_153524`

Contract:
- focuses on the V190/V191 near-frontier high-WR micro bucket (`FVG_Demand + BULL_CONTINUATION + low chase`);
- tests whether executable runner exits can turn micro target wins into usable expectancy;
- shadow-only.

Best variant: `close_10d`
- base rows = 503;
- `n=500`, `WR=48.40%`, `Avg=2.3845%`, `median=-0.2437%`;
- `min_year_n=5`, `all_year_WR_min=23.30%`;
- exits: `RUNNER_TIME_CLOSE=273`, `SL=205`, `GAP_SL=22`;
- T+1 violations = 0.

Decision: `V193_NO_RESEARCH_CHILD_PASS__FVG_MICRO_RUNNER_CLOSED`.

Root cause: the prior high WR came from tiny BSL/1.5R targets and was micro-profit pollution. When allowed to run, the bucket loses win-rate/year stability and is not a production child.

### V194 — HTF structural context gate over V129 realistic exits

Artifact: `/root/.hermes/smc_audit/v194_htf_structure_gate_fast_20260625_155004`

Contract:
- pre-entry higher-timeframe structure/position features from raw K-line cache;
- evaluates on V129 realistic target exits (`v129_pnl_pct`), non-overlap vs V175;
- no outcome fields used in selector; shadow-only.

Best rule:
- `market=BULL_CONTINUATION & chase<=0.5 & rr>=0.8`
- `n=90`, `WR=74.44%`, `Avg=0.2766%`, `min_year_n=1`, `all_year_WR_min=0%`, `micro=7.78%`;
- T+1 violations = 0.

Decision: `V194_NO_RESEARCH_CHILD_PASS__HTF_STRUCTURE_GATE_CLOSED`.

Root cause: HTF structure and target geometry filters cannot rescue the V128 supply under realistic target exits. They reduce sample size without fixing target quality or POI failure.

## Updated closed paths

Closed after V177-V194:
1. Generic exit overlays on V175.
2. TIME-row attribution as a single homogeneous bug.
3. Historical 60min production exits with current 60min coverage.
4. V128 source-side scalar filters.
5. Delayed wait-more-bars after V128 reclaim.
6. V167 leftover child expansion.
7. Simple fixed runners for V167 leftover child.
8. Classical sweep-CHOCH-OB raw generator.
9. V85 runner expansion.
10. Market breadth + target geometry filtering.
11. Micro-HL post-reclaim confirmation.
12. Accumulation breakout retest raw generator.
13. Impulse demand retest raw generator.
14. Cost-control/AVWAP-style pre-entry gate.
15. Limit-up/attention memory filter.
16. Board/peer confirmation filter.
17. Limit-up attention impulse → demand-zone retest raw generator.
18. FVG high-WR micro bucket runner conversion.
19. HTF structural gate over V129 realistic exits.

## Current conclusion

V175 remains the only verified production-usable artifact in this chain. The active-pick materialization can be refreshed separately if needed, but that is production sync work, not strategy research.

No post-V175 research child from V177-V194 passes the declared gates. The repeated failure is not exit mechanics and not simple context filtering; it is candidate supply quality.

## Next direction likely to produce qualitative change

Stop using V128/V167/V175 rows as the search substrate. Build a new event-source generator that labels actual smart-money absorption before entry. The next candidate should be created from raw K-line lifecycle, not from old POI rows:

1. Detect liquidity event or board/attention shock.
2. Require absorption evidence before entry:
   - failed breakdown below demand with close reclaim;
   - lower wick dominance at the same zone across multiple tests;
   - volume contraction on pullback + expansion on reclaim;
   - no close below zone between touch and reclaim.
3. Require a pre-entry target that is not micro:
   - known liquidity target must provide enough distance;
   - reject if target RR/expected move is too small before backtest.
4. Replay with semantic exits and T+1 from construction.
5. Only then compare non-overlap child against V175.

Do not continue scalar filters over V128/V129 unless adding a genuinely new pre-entry absorption feature; prior scalar/context/filter paths are now closed.

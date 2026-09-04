# V183-V198 post-V175 daily-OHLCV research closure

Date: 2026-06-25

## Trigger

Use when deciding whether to keep iterating after V175 semantic split / V128 / V167 / V172 research, especially when the user asks what is done, what is not done, and what direction remains.

## Predeclared gates

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

Research child usable:
- 100% non-overlap vs V175;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

Unusable:
- outcome leakage;
- T+1 violation;
- high WR created by micro/BE targets;
- low n or year concentration;
- relabeling/filtering old V167/V172/V175 rows without new supply;
- 60min claim with insufficient historical coverage.

## Results after V180-V182

Additional daily/full-market paths were tested and closed:

- V183/V184 fresh context/SSL/CHOCH demand generators: unusable; WR around 31-32%, high SL, no production/child pass.
- V186 micro-HL takeover: best `n=603`, `WR=44.44%`, `Avg=-0.293%`, closed.
- V187 accumulation breakout retest: best `n=8`, too small/unstable, closed.
- V188 impulse demand retest: best child `n≈1595`, `WR≈42.13%`, `Avg≈0.104%`, closed.
- V189 cost-control pre-entry gate over V129: no frontier; high-WR rules were mostly micro-profit pollution (`micro_profit_pct` often 60%+), closed.
- V190 limit-up attention memory: no frontier, closed.
- V191 board/peer confirmation: no frontier, closed.
- V192 limit-up demand retest: best `n=3177`, `WR=33.46%`, `Avg=0.2884%`, closed.
- V193 FVG attention runner replay: best `n=500`, `WR=48.4%`, `Avg=2.3845%`, year instability, closed.
- V194 HTF structure gate: best `n=90`, `WR=74.44%`, `Avg=0.2766%`, closed.
- V195 raw absorption generator: `n=1636`, `WR=43.4%`, `Avg=2.3344%`, year min WR 18%, closed.
- V196 absorption quality frontier and V197 absorption+breadth context: no frontier, closed.
- V190 breadth-regime gate (previous-trading-day breadth + V129 target geometry): `rules_tested=1305`, `frontier_count=0`; best rules had combined WR near 84 but Avg only ~5.1-5.3 and micro >2%, closed.

V198 closure artifact:
- `/root/.hermes/smc_audit/v198_post_v175_research_closure_20260625_170818/`
- Decision: `POST_V175_DAILY_OHLCV_RESEARCH_CLOSED__NO_NEW_PRODUCTION_ENGINE`.
- Indexed 105 no-write/closed research artifacts, no new frontier.

## Decision

Under the current daily OHLCV + V128/V129/V167/V175 artifact set, post-V175 research is closed. V175 remains the production baseline; no new production-quality child engine was found.

Do **not** keep looping over daily scalar filters or near-identical daily generators; this becomes endless overfitting without qualitative change.

## Only remaining directions with real qualitative potential

1. **Historical intraday data acquisition**: fill 60min/15min history for 2023-2026, then replay V175 TIME/entry confirmation with executable T+1-compatible rules. Current coverage was only `9/65 = 13.85%`, so production claims are blocked until data exists.
2. **Material new ex-ante data source**: true sector/board flows, order-flow/auction data, or fundamentals that are known before entry. Outcome fields, realized PnL, MFE/MAE, exit reason, or target-hit labels remain forbidden as selectors.
3. **Production hygiene only**: current V175 active picks may be stale relative to latest V128 snapshot; rematerialize only through the verified V175/V172 chain and re-run frontend/API pollution checks before any production write.

If none of these data/source changes is available, stop research rather than continue daily-OHLCV iteration.

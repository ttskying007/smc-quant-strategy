# V183-V185 fresh generator negative closure

Date: 2026-06-26

## Trigger

Use after V175/V180-V182 when deciding whether to continue with fresh SMC candidate generators from raw daily K-line data.

## Predeclared gates

Production upgrade usable:
- non-leaking source-side rule;
- T+1 violations = 0;
- combined/new engine `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API mutation before dry-run passes.

Research child engine usable:
- 100% non-overlap vs V175 if combined;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

## Completed fresh-generator attempts

All were shadow-only/audit-only, from raw daily K-line cache, no V128/V167/V175 rows used as input, and no frontend/watchlist/API writes.

### V183 — SSL sweep → CHOCH → Demand OB reclaim

Artifact: `/root/.hermes/smc_audit/v183_fresh_ssl_reclaim_demand_ob_generator_20260626_091941/`

Mechanism:
- confirmed prior swing low SSL sweep;
- bullish structural reclaim/CHOCH;
- last bearish demand OB;
- post-CHOCH touch + reclaim;
- next-open entry, T+1 enforced, SL under zone, TP via BSL prior high or 1.5R.

Result:
- `n=837`, `WR=41.58%`, `Avg=1.7713%`, `min_year_n=92`, `all_year_WR_min=35.87%`, `micro=2.03%`, `T+1=0`.
- Best bucket still far below gate: `STRUCT_1P5R n=105 WR=56.19 Avg=2.1288 min_year=12`.

Decision: `FAIL_NO_WRITE`.

### V184 — PO3 ACC→MAN→DIS breaker reclaim

Artifact: `/root/.hermes/smc_audit/v184_fresh_po3_acc_man_dis_generator_20260626_092144/`

Mechanism:
- accumulation range;
- SSL manipulation below range;
- distribution breakout above range;
- breaker/demand retest + reclaim;
- next-open T+1 trade.

Result:
- `n=4574`, `WR=43.31%`, `Avg=0.7444%`, `all_year_WR_min=29.45%`, `micro=1.25%`, `T+1=0`.
- Best tight PO3 bucket: `n=728`, `WR=45.33%`, `Avg=0.7479%`, `all_year_WR_min=33.96%`.

Decision: `FAIL_NO_WRITE`.

### V185 — fresh Demand OB true takeover from K-line only

Artifact: `/root/.hermes/smc_audit/v185_fresh_demand_ob_true_takeover_20260626_092633/`

Mechanism:
- structural bear-risk/discount context using 60-bar range position and drawdown;
- bearish demand OB;
- bullish impulse confirms demand;
- later pullback into OB zone;
- strict 2-3 bar true takeover/reclaim;
- next-open T+1 trade, fixed 1.5R target.

Result:
- `n=40595`, `WR=44.32%`, `Avg=0.3506%`, `all_year_WR_min=0/34.36% after removing tiny old years`, `micro=1.24%`, `T+1=0`.
- Exhaustive source-feature threshold search over V185 rows (risk, zone width, DD60, range position, reclaim body, bull count) found no usable frontier. Best robust combinations stayed around `WR≈47-48%`, `Avg≈0.6-0.8%`, `yearWRmin≈20-40%`.

Decision: `FAIL_NO_WRITE`.

## Interpretation

These failures are useful because they disprove three tempting directions:
1. Daily SSL sweep + reclaim alone is not enough.
2. PO3 range manipulation on daily A-shares is too noisy as a standalone supply layer.
3. Naive K-line-only Demand OB true-takeover generation is massively over-inclusive; V175 quality is not reproduced by simply rewriting the label or using basic OB/reclaim geometry.

## Updated next direction

Do not continue scalar filtering of V183/V184/V185.

The next qualitative research direction must isolate what V128/V167 contributed that naive raw-Kline generators missed. Specifically compare V175 winners/losers and V185 failures at the event-construction level:
- exact V128 independent-parallel candidate construction and dedupe score;
- V132 features (`v132_reclaim_class`, `v132_bull_count_3`, `v132_post_zone_pullback_depth_pct_3`);
- why V175/V167 source rows are sparse while V185 emits 40k+ noisy rows;
- derive a stricter non-leaking generator contract before coding another generator.

Until that contract is identified, V175 remains the only production-valid artifact and V183-V185 are closed negative research paths.
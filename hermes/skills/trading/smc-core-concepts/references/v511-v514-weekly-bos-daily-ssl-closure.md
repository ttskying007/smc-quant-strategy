# V511–V514 Weekly BOS context → Daily SSL reversal closure

Session date: 2026-07-15

Use when continuing pure-structure SMC research after V510. This branch tested a genuinely cross-timeframe ontology rather than another threshold or exit variant.

## Frozen ontology

1. Completed weekly 2L/2R pivot high is broken by a weekly close of at least 0.3%.
2. The nearest confirmed weekly swing low before BOS becomes the protected low; a later completed-week close below it invalidates the context.
3. While the weekly bullish BOS context is active, daily 3L/3R SSL is raided by wick at least 0.3% and closes back above.
4. Within 10 sessions, daily close breaks the raid-time visible swing high by 0.2% (bull CHOCH).
5. Scan backward at most 6 daily bars from CHOCH for the nearest bearish candle as Demand OB.
6. Require first post-CHOCH overlap touch, later close reclaim, later hold above zone, then next-session-open eligibility; close below zone cancels.
7. Frozen execution: SL=daily raid low×0.99; target=nearest higher weekly swing high confirmed by hold; time30; fee 0.2%; gap-aware, same-bar collision resolves to SL, strict T+1, one position per symbol, search count 1.

## Verified result

- Full local universe: 4,897 symbols.
- Outcome-blind seeds: 7,938; yearly support 2023/24/25/26 = 201/2,262/3,665/1,809.
- Independent raw-bar Oracle: 7,938/7,938 PASS; no forbidden outcome fields.
- Serial closed trades: 7,387; T+1=0; chronology=0; duplicates=0; serial overlap failures=0.
- Aggregate: gross WR 64.1262%; net≥0.8 WR 54.2304%; AvgNet +0.1247%; payoff 0.6237; PF 1.0407; planned RR 0.9408; SL 31.3659%.
- 2023 AvgNet -1.4323%, 2024 -0.7621%, 2025 +0.8425%, 2026 -0.0937%.

## Decision

Close this ontology. Weekly bullish BOS permission raises headline WR but does not fix the small-win/large-loss structure: average win +5.0964% versus average loss -8.1717%. Only 2025 is economically positive; 2023, 2024, and 2026 fail. Do not reopen via weekly context, SSL/CHOCH window, OB lookback, SL, target, hold, year, or regime variants.

Artifacts: `v511_weekly_bos_daily_ssl_reversal_latest.json`, `v512_weekly_bos_daily_ssl_reversal_oracle_latest.json`, `v513_weekly_bos_daily_ssl_reversal_frozen_t1_replay_latest.json`, `v514_weekly_bos_daily_ssl_reversal_metric_audit_latest.json`.

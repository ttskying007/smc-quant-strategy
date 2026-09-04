# V102 Balanced Volume Gate Lesson

## Trigger
Use this when the SMC backtest page shows very few production trades in a date window, especially when the user reports counts like `20240101~latest only has ~50 trades` or says trade count / RR is insufficient.

## Durable lesson
A low backtest count may be a frontend window/filter artifact, not missing data. First split:
1. Full production count in the promoted report.
2. Window count by `entry_date`.
3. Rows excluded by date window.
4. Gate loss by `v100_tier`, `production_grade`, `combo_contract_key`, `market_state`, `mtf_trend_permission`, and structure fields.

In the V101 case, production was 59 full / 54 in `20240101~20260616` because the page correctly excluded 5 trades from 2023. The actual bottleneck was the production gate: V101 preserved only V100 `A_PRODUCTION_CORE`.

## Avoid
Do not blindly promote all B/C or BOS candidates. In the audited V101 data:
- `B_OBSERVE_HIGH_WR` was high quality but mostly `BOS_CONTINUATION` / MTF conflict.
- Full `C_ROBUST_OBSERVE_ONLY` added volume but raised SL rate materially.
- Full `BOS_CONTINUATION` remained too noisy and should not be promoted as a class without structural signal audit.

## Proven workflow
Run gate-loss tables and search for stable conjunctions instead of loosening one threshold. The successful class-level gate was:
- `v100_tier in {A_PRODUCTION_CORE, B_OBSERVE_HIGH_WR, C_ROBUST_OBSERVE_ONLY}`
- `market_state == MIXED`
- `daily_structure_state == DOWN_STRUCTURE`
- structural TP2/net/risk checks retained (`tp2_rr >= 5`, `expected_tp2_net_pct >= 0.8`, bounded `risk_pct`)

This raised the 2024+ window from 54 to 168 trades while keeping high quality in the audited run: WR about 91%, avg net about 3.9%, SL rate under 9%, and page RR about 5.23x.

## Frontend sync checklist
When promoting a new contract layer (e.g. V102):
- Write an independent script and output directory; do not overwrite the previous version.
- Preserve compatibility aliases if the frontend still reads previous prefix names (`v101_*.json`).
- Update promoted directory priority, trade cache file, report loader, active pick mtime, active pick merge path, and version badge.
- Ensure `_v100_production_rows()` recognizes the new production boolean (e.g. `production_eligible_v102`).
- Re-verify `/api/summary`, `/backtest?start=...&end=...`, `/api/picks`, `/api/live-prices`, and Kline badge after restart.

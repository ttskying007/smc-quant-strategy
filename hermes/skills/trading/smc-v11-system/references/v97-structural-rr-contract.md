# V97 Structural RR Contract: replace fixed micro-R ladders with SMC target-space gates

## Trigger
Use this note when Lei rejects TP/SL design as structurally wrong, especially when production candidates show fixed short-profit ladders like `0.8R / 1.5R / 3R`, `1R / 2R / 3R`, or low `tp1_rr` values that cannot cover realistic trading costs.

## Durable lesson
Do **not** repair this class of issue by changing constants from `0.8R` to `5R`. That is still a fixed RR target and violates the SMC logic. The correct design is:

1. Detect/confirm POI: Demand OB / FVG / Breaker / OTE.
2. Confirm executable entry: zone touch + reclaim/reaction/MSS/pinbar, with T+1 enforced.
3. Place SL at structural invalidation:
   - POI low below buffer, or
   - SSL sweep low below buffer, or
   - last HL / confirmed structural low below buffer.
4. Scan **known/pre-entry** structure targets above entry:
   - micro BSL / prior swing high,
   - meso BSL / EQH,
   - macro BSL / major high,
   - supply POI / weekly high / BOS/CHOCH break target.
5. Compute target-space RR from structure: `TP1_R`, `TP2_R`, `TP3_R`.
6. Gate production by structural space:
   - A: `TP2_R >= 5`, `TP3_R >= 8`, legal structural SL, target is BSL/EQH/major high/supply POI.
   - B: `TP2_R >= 4`, `TP3_R >= 6`, legal SL, clear target but weaker space.
   - C: `TP2_R 2~4`, watch only.
   - D: `TP2_R < 2`, no structural TP, or only weak micro target: reject.
7. Exits: TP1 is protection only; TP2 is main take-profit; TP3 is runner.

## Verification requirements
- Audit current active picks and backtest rows for `tp*_rr`; production rows must have zero `A_PRODUCTION` candidates with `TP2_R < 5` or `TP3_R < 8`.
- Run full-market scan/backtest, not a small sample.
- Report grade distribution (A/B/C/D), RR distributions, exit counts, WR, avg PnL, SL rate.
- Sync frontend/API in the same session: `/api/picks`, `/api/live-prices`, K-line fields, and scheduler/daily ops if production sourcing changes.
- Do not allow legacy V90/V91 low-RR candidates to leak into production after the structural contract is introduced.

## Session implementation reference
In the V97 repair session, the class-level implementation pattern was:
- add a structural contract scanner that preserves the V85/V91 POI/entry layer but replaces fixed micro ladders with structural target scanning and grade gates;
- update daily ops to run the structural scanner;
- update frontend merge logic to prefer V97 active picks and suppress legacy V90/V91 low-RR sources when V97 exists;
- verify API candidates have no missing date/zone/cost/volatility/grade/RR fields and no A-grade low-RR candidates.

This is a pattern, not a requirement to reuse the exact version number or file paths in future systems.

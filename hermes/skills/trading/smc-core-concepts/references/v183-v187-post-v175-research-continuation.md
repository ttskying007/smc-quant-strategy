# V183-V187 post-V175 research continuation

Date: 2026-06-26

## Trigger
Use when continuing SMC research after V175/V180-V182 closure and the user asks what direction remains valid.

## Predeclared usable/unusable gates
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

## Completed new research

### V183 — classical lifecycle generator from kline cache
Artifact: `/root/.hermes/smc_audit/v183_new_supply_lifecycle_generator_20260626_082239/`
- New source, not a V128/V167 filter: confirmed SSL sweep -> CHOCH -> demand OB -> retrace/reclaim -> T+1 entry.
- Dedup candidates: 38.
- Best/ALL: `n=38`, `WR=36.84%`, `Avg=-0.1927%`, SL+GAP_SL ≈ 63%.
- Decision: unusable. Strict classical lifecycle is too sparse and still wrong in A-share daily data.

### V184 — compression breakout continuation generator
Artifact: `/root/.hermes/smc_audit/v184_continuation_supply_generator_20260626_082505/`
- New source: compression/range -> breakout -> demand base -> pullback reclaim -> T+1 entry.
- Dedup candidates: 13,457.
- Best buckets still only ~42-52% WR and ~0.6-1.4% Avg; no child/production pass.
- Decision: unusable. Broad continuation/reclaim supply is not enough; it creates high SL rate (~54%).

### V185 — full-market structural breadth context
Artifact: `/root/.hermes/smc_audit/v185_market_structure_breadth_context_20260626_083312/`
- Ex-ante full-market breadth from kline cache, known before entry:
  - `upper60_pct`: share of stocks closing in upper half of 60d range;
  - `break20_pct`: share breaking prior 20d high;
  - `recover20_pct`: share recovered >8% above 20d low;
  - `down20_pct`: share near 20d lows.
- On V184: improves Avg to ~2-4% in some buckets but WR remains far below gate.
- On V175: strong regime effect but too small for production:
  - `down20_pct<=15`: `n=98`, `WR=88.78%`, `Avg=6.6128%`, yearWRmin=85.71, T+1=0, but n/min_year insufficient and micro=1.02%.
  - `upper60_pct<=25 & recover20_pct>=55`: `n=41`, `WR=95.12%`, `Avg=6.9155%`, insufficient n/year coverage.
- Decision: breadth is a real qualitative context axis, not a production upgrade alone.

### V186/V187 — V167 leftover + breadth close frontier
Artifacts:
- `/root/.hermes/smc_audit/v186_v167_leftover_breadth_frontier_20260626_083534/`
- `/root/.hermes/smc_audit/v187_v167_breadth_numpy_frontier_20260626_084921/`

Best close-frontier combinations:
- V186 top: V175 base + child `v132_bull_count_3>=3 & risk_pct4_8 & recover20_pct<=55 & down20_pct<=25`
  - Child: `n=38`, `WR=92.11%`, `Avg=7.1278%`, T+1=0, but unstable year coverage.
  - Combined: `n=285`, `WR=84.91%`, `Avg=6.1931%`, minYear=39, yearWRmin=84.31, micro=1.05%, T+1=0.
  - Fails production by tiny margins: Avg < 6.2, minYear < 40, micro > 1%.
- V187 top: `bull3>=3 & risk5_9 & upper<=35 & break<=5 & down<=25`
  - Child: `n=26`, `WR=92.31%`, `Avg=8.0196%`.
  - Combined: `n=273`, `WR=84.62%`, `Avg=6.2369%`, yearWRmin=82.98, but minYear=39 and micro=1.10%.
- V187 robust-year near-frontier: `bull3>=3 & risk4_8 & pull<=1 & break<=5 & down<=15`
  - Child: `n=34`, `WR=94.12%`, `Avg=7.3475%`.
  - Combined: `n=281`, `WR=85.05%`, `Avg=6.2064%`, minYear=41, yearWRmin=83.67, but micro=1.07%.

Decision: still no production pass. These are close-frontier research candidates only.

## Critical mechanism finding
`v132_bull_count_3` is a real signal-quality axis:
- V175 rows with `v132_bull_count_3>=3`: `n=85`, `WR=92.94%`, `Avg=7.7928%`, micro=0, all years >90% WR, but n is too small.
- V175 rows with `v132_bull_count_3==2`: `n=162`, `WR=79.01%`, `Avg=5.1345%`, contains all 3 micro-profit rows.

This explains why close-frontier children all start with `bull3>=3`: three-bar post-reclaim takeover is the strongest observed non-leaking source-side semantic.

## Current direction after V187
Closed/unusable:
1. Strict classical SSL->CHOCH->OB lifecycle as a new generator (V183).
2. Broad compression breakout continuation as a new generator (V184).
3. V184 + breadth as production path.
4. V167 leftover + breadth as production upgrade: close but still fails hard gate.
5. Any claim that V186/V187 is production-ready; it is not.

Next research with real potential:
- Build a new generator with `v132_bull_count_3>=3` as a first-class supply condition, not a post-filter.
- The generator must increase the count of true 3-bar takeover setups while preserving Avg and year stability.
- Focus on finding more `bull3>=3` supply in current/new POI sources, not adding more scalar filters to V175.
- Production remains V175 until a child/combined candidate clears every gate.

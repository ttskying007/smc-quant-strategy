# V225-V227 participation layer continuation

Date: 2026-06-27

## Trigger
Use after V222-V224 when continuing post-V185 research. The remaining valid direction was a real sector/industry participation layer or a stronger peer-breadth rule; this closes the next iteration.

## Gates
Post-V185 production improvement still requires:
- source-side / non-leaking selector only;
- T+1 violations = 0;
- `n >= 300`, `min_year_n >= 40`;
- `WR >= 87%`, `AvgPnL >= 6.8%`, `all_year_WR_min >= 84%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API mutation before dry-run and endpoint validation.

Research-only usable requires at least:
- `n >= 260`, `min_year_n >= 35`, `WR >= 88%`, `AvgPnL >= 6.8%`, `all_year_WR_min >= 84%`, `micro <= 1%`, `T+1=0`.

## Artifacts
- V225 Baostock industry participation probe: `/root/.hermes/smc_audit/v225_baostock_industry_participation_probe_20260627_031854/`
- V226 peer + industry pair-rule probe: `/root/.hermes/smc_audit/v226_peer_plus_industry_pair_rule_probe_20260627_032029/`
- V227 independent audit: `/root/.hermes/smc_audit/v227_v226_research_pair_independent_audit_no_write_20260627_032359/`
- Temporary scripts: `/tmp/v225_baostock_industry_participation_probe.py`, `/tmp/v225_real_sector_participation_probe.py`.

## V225 industry result
Baostock `query_stock_industry()` succeeded in a temporary venv and returned:
- 5,530 industry rows;
- 5,207 classified symbols;
- 83 CSRC industries;
- 4,651 symbols with local K-line cache coverage;
- V185 coverage: 334/334 rows, 0 missing industry, 1 missing breadth row.

V225 diagnostics:
- losers had higher previous-day industry strong breadth (`v225_ind_strong1_pct` loss mean 29.80 vs win mean 23.81);
- best source-aware rule was `keep all V185_CHILD; keep V175_BASELINE only when v225_ind_up1_pct <= 93.333333`:
  - `n=288`, WR `88.54%`, Avg `6.7925%`, minYear `36`, yearWRmin `84.21%`, micro `1.04%`, T+1 `0`.
- Decision: `V225_NO_INDUSTRY_BREADTH_GATE_PASS__NO_WRITE`.

Important caveat: Baostock industry classification is a current snapshot (`updateDate=2026-06-22` in this run), not point-in-time historical membership. Even a passing rule would require point-in-time industry audit before production.

## V226 pair-rule result
V226 merged V222 peer-prefix breadth and V225 industry features, then searched source-aware pair rules. It found 2 research-pass rules, but 0 production-pass rules.

Best audited research-pass rules:
1. `keep all V185_CHILD; keep V175_BASELINE only when v222_p2_strong1_pct<=56.521739 AND v222_all_up1_pct<=89.2172`
   - `n=300`, WR `88.3333%`, Avg `6.8006%`, minYear `36`, yearWRmin `85.00%`, micro `1.00%`, loss_n `35`, T+1 `0`.
2. `keep all V185_CHILD; keep V175_BASELINE only when v222_p3_weak1_pct>=0.857843 AND v222_board_up1_pct<=92.627599`
   - `n=303`, WR `88.1188%`, Avg `6.8089%`, minYear `38`, yearWRmin `84.2105%`, micro `0.9901%`, loss_n `36`, T+1 `0`.

Decision: `V226_PAIR_RESEARCH_PASS__NO_WRITE`.

## V227 independent audit
V227 re-applied the two V226 rules from raw `v222_enriched_rows.csv` and verified:
- selector leak fields: `[]`;
- time-order bad count: `0` (`v222_prev_market_date < entry_date`);
- both rules remain research-only and fail production due to `min_year_n < 40`;
- current V185 active rows: 6/6 pass both rules, so these rules do **not** change current active picks.

Decision: `V227_V226_RULES_RESEARCH_ONLY__PRODUCTION_FAIL_MIN_YEAR__NO_WRITE`.

## Direction closure
V225-V227 confirms the participation layer is real and directionally useful, but still not production-upgrade quality:
- industry snapshot alone: no gate pass;
- peer/market pair rule: research pass, production fail on year coverage;
- current active picks unchanged;
- no frontend/watchlist/API writes.

Next valid directions:
1. If continuing research, do not route V226/V227. Use them only as a research overlay and seek a genuinely new candidate supply layer or point-in-time industry/sector data.
2. If production stability is the priority, keep V185 as production baseline and focus on cron/live-guard/field consistency.
3. Do not keep stacking scalar filters unless they beat the V185 production gate with `min_year_n>=40`; high WR with low year coverage is closed as non-production.

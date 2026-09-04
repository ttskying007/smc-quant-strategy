# V158–V160 Non-leak lifecycle stability lesson

Date: 2026-06-22

Context: V154/V152 lifecycle candidate research after cancel-addback/no-micro-pnl cleanup. Scope was research-only; no production/frontend/watchlist writes.

## Key results

- V158 found a non-leaking lifecycle candidate:
  - Rule: `TRUE_TAKEOVER_2` must have either strict secondary confirmation or low entry chase (`entry_chase_above_zone_pct <= 3`), and non-strict takeovers with reclaim-body exhaustion (`v132_reclaim_bull_body_pct > 86.6`) are downgraded to `WATCH_ONLY`.
  - Metrics: n=214, WR=84.11%, Avg=+3.5357%, min_year_n=35, 2024 WR=78.05%, T+1 violations=0.
  - Decision: candidate found but research-only.
- V159 monthly/rolling stability audit showed aggregate yearly metrics were not sufficient:
  - bad months with n>=3 and WR<60: 2 (`202405`, `202406`).
  - weak months with n>=3 and WR<78: 9.
  - rolling 30-trade windows with WR<70: 1 (`20240507`→`20240902`, WR=66.67%).
  - Remaining losses were almost entirely fast adverse movement (`v138_mae_pct <= -4`), which is post-entry and must not be used as a buy selector.
- V160 robust monthly rule search failed to find a production-stable non-leak hard gate under the tested pure SMC/pre-entry predicates:
  - Best fallback: `TT2_CONFIRM_OR_CHASE_LE_3_5 + NONSTRICT_BODY_LE_86_6`.
  - Metrics: n=225, WR=84.00%, Avg=+3.5105%, min_year_n=35, 2024 WR=78.16%, rolling30_bad=0.
  - Still has 1 bad month (WR<60, n>=3) and 8 weak months (WR<78, n>=3), so robust_pass=false.

## Rule discipline

Do not promote V158/V160 directly just because aggregate WR/Avg pass. Monthly and rolling stability must pass too. If no pure SMC/pre-entry gate removes the weak months without destroying coverage, the next step is not TP/SL tuning and not market-breadth leakage; it is a dry-run scanner contract plus live-field availability audit:

1. Verify every required field is available at scanner time without post-entry outcome fields.
2. Map the candidate as `shadow_only` / `WATCH_ONLY` first.
3. Run recent full-market scanner coverage and frontend/API isolation checks.
4. Only after dry-run contract is clean, consider production promotion.

## V162–V163 follow-up findings

- V162 weak-month attribution found V160 still cannot be promoted:
  - Base: n=225, WR=84.00%, avg=+3.5105%, min_year_n=35, T+1=0.
  - Still has bad60=1 (`202405`) and weak78=8.
  - Best single scanner-time bad60=0 filter is reclaim body cap (`v132_reclaim_bull_body_pct <= 87.1077`), but it does not remove weak months, so it is not a complete production gate.
  - Artifacts: `/root/.hermes/smc_audit/v162_v160_weak_month_attribution_20260622/`.
- V163 scanner integrity audit found the key hidden bug in the dry-run selector:
  - `apply_v160()` used `(strict3 OR entry_chase<=3.5) AND body<=86.6` and did **not** require `TRUE_TAKEOVER_2/TRUE_TAKEOVER_3_STRICT`.
  - Historical V160 rows were already takeover-clean (225/225), hiding the bug.
  - Real V161 scanner recent45 V160 BUY rows were polluted: 1726 BUY rows, 1267 were FAILED/RECOVERY/UNCLEAR, only 403 passed `(TT2 OR TT3_STRICT) AND body<=87.1077`.
  - Latest clean pass date `20260617` had only 2 rows.
  - Decision: `V160_DRY_RUN_RULE_HAS_SCANNER_INTEGRITY_BUG__DO_NOT_PROMOTE`.
  - Artifacts: `/root/.hermes/smc_audit/v163_scanner_rule_integrity_audit_20260622/`.

## Artifacts

- `/root/.hermes/smc_audit/v158_non_leak_smc_lifecycle_rebuild_20260622/`
- `/root/.hermes/smc_audit/v159_v158_stability_fragility_audit_20260622/`
- `/root/.hermes/smc_audit/v160_v158_robust_monthly_rule_search_20260622/`
- `/root/.hermes/smc_audit/v162_v160_weak_month_attribution_20260622/`
- `/root/.hermes/smc_audit/v163_scanner_rule_integrity_audit_20260622/`
- Scripts:
  - `/root/.hermes/scripts/v25/v158_non_leak_smc_lifecycle_rebuild.py`
  - `/root/.hermes/scripts/v25/v159_v158_stability_fragility_audit.py`
  - `/root/.hermes/scripts/v25/v160_v158_robust_monthly_rule_search.py`
  - `/root/.hermes/scripts/v25/v162_v160_weak_month_attribution.py`
  - `/root/.hermes/scripts/v25/v163_scanner_rule_integrity_audit.py`

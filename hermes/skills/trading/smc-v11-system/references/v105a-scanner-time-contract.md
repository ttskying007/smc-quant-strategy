# V105-A scanner-time contract lesson

Use this when a historical SMC gate looks strong after secondary audit, but the user asks whether it is production-ready or what research direction should continue.

## Session outcome

V105-A was derived as a quality/coverage improvement over V104-B:

```text
V104B = G1_STRICT_STRUCTURAL_TP2 OR G4_RISK_1P1_NO_MICROHL_NO_B_TIER
V105A = V104B OR ((NOT V104B) AND 0 < tp2_rr <= 5.059)
```

Historical clean audit result:

| Version | n | WR | avg | SL |
|---|---:|---:|---:|---:|
| V103-A clean | 170 | 88.82% | 3.9192% | 11.18% |
| V104-B | 122 | 90.98% | 4.0343% | 9.02% |
| V105-A | 144 | 91.67% | 4.0435% | 8.33% |
| V105-A reentry added | 22 | 95.45% | 4.0945% | 4.55% |

Year stress passed in the historical pool: 2023=15/86.67%/13.33%SL, 2024=10/90%/10%SL, 2025=90/92.22%/7.78%SL, 2026=29/93.10%/6.90%SL. T+1=0 and event_after_entry=0.

## Critical promotion blocker

The same V105-A selector was audited against the real V90 full-market scanner output (`v128_parallel_shadow_candidates.json`, 38,952 rows). Scanner-time selector availability failed:

| Field | present | missing |
|---|---:|---:|
| production_eligible_v102 | 0 | 38952 |
| v100_tier | 0 | 38952 |
| mtf_trend_permission | 0 | 38952 |
| tp2_target_type | 0 | 38952 |
| sl_mode | 0 | 38952 |
| risk_pct | 38952 | 0 |
| tp2_rr | 0 | 38952 |
| expected_tp2_net_pct | 0 | 38952 |

Decision label:

```text
V105A_HISTORICAL_CANDIDATE_NOT_PROMOTION_READY__SCANNER_CONTRACT_MISSING_FIELDS
```

## Rule to encode for future work

Do **not** promote a historically strong secondary audit gate unless the true current full-market scanner can compute every selector field before BUY without outcome/post-entry leakage.

A gate that depends on `v100_tier`, `production_eligible_v102`, `mtf_trend_permission`, `tp2_target_type`, `sl_mode`, or `tp2_rr` is not scanner-usable until those fields are rebuilt in scanner-time form.

## Correct next direction

Stop mining the same historical 170-row pool once a strong candidate is found and scanner contract fails. Move to V106:

1. Rebuild scanner-time equivalents:
   - `mtf_trend_permission` from weekly/daily/60m state using only bars available at entry decision time.
   - `tp2_rr` from known prior BSL / swing high / EQH targets strictly before entry.
   - `tp2_target_type` as structural target classification (`micro_BSL`, `prior_swing_high`, `EQH`, `none`).
   - `sl_mode` from POI low / micro-HL / buffer logic available in scanner payload.
   - `v100_tier` only as a non-outcome proxy; do not copy historical tier if it was derived from realized performance.
2. Or abandon V105-A historical fields and search directly on V90 scanner-time fields: `risk_pct`, `market_state`, `poi_source`, `source_gap_atr`, `source_mid_body_atr`, `v85_zone_width_pct`, `reclaim_close_above_zone_pct`, `reclaim_close_pos`, `touch_to_reclaim_bars`, `entry_chase_above_zone_pct`, `combo_family`, `event_type`.
3. Re-run latest full-market scanner and write an audit report with:
   - scanned_symbols, latest_market_date, source rows, selector-evaluable rows
   - required field missing counts
   - outcome field leak count
   - T+1 and event/entry ordering checks
   - explicit decision: promotion-ready vs historical-candidate-only

## Artifacts pattern

Use a research/pre-promotion script that writes only audit/research artifacts first, e.g.:

```text
/root/.hermes/scripts/v25/v105a_structural_tp2_reentry.py
/root/.hermes/smc_opt_v105a_structural_tp2_reentry/v105a_report.json
/root/audit_*/v105a_scanner_contract_audit.md
```

Do not change frontend routing or production watchlists until scanner-time contract passes.
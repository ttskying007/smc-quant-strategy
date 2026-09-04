# V110 RANGE_TRANSITION Dedup + Boundary Audit Lesson

Use this reference when continuing RANGE_TRANSITION / BULL_EXPANSION SMC strategy research after a semantic filter looks promising but sample stability is unclear.

## Trigger

A prior rule accepts RANGE_TRANSITION rows based on confirmation delay or second structure confirmation, but the candidate set contains repeated `symbol + entry_date` rows from multiple families (`REVERSAL` / `CONTINUATION`) and headline WR looks better than production readiness.

## Required audit order

1. **Deduplicate before judging quality**
   - Collapse to one row per `symbol + entry_date` before reporting WR/SL/month stability.
   - Use deterministic ex-ante ranking only; do not use `net_pnl_pct`, `exit_reason`, MFE/MAE, or any outcome field to choose the canonical row.
   - A safe rank is: in confirmation window first, lower `risk_pct`, lower `chase_pct`, `event_to_entry` closest to the intended boundary, then stable family name.

2. **Compare timing boundaries explicitly**
   - Report at least: `8-21`, `9-21`, `10-21`, `11-21`, `12-21`, `second-confirm-only`, and `event_to_entry=8` alone.
   - Do not infer that a broad window is valid just because a later subset performs well.

3. **Dissect accepted losses by ex-ante fields**
   - For all accepted losers, table: `symbol`, `entry_date`, `event_to_entry`, `second_confirm_before_entry`, `exit_reason`, `net_pnl_pct`, `risk_pct`, `retrace_pct`, `chase_pct`.
   - Bucket accepted and losing rows by `risk_pct`, `retrace_pct`, `chase_pct`, and `event_to_entry`.
   - If all losses have `second_confirm_before_entry=False`, treat second-confirm semantics as still unproven rather than solved.

4. **Monthly stability is a hard gate**
   - A high WR small subset is still research-only when stable months are sparse.
   - Require enough rows per month; months with `n=1/2` are coverage notes, not stability proof.

## V110 empirical lesson

After deduplicating V109 RANGE_TRANSITION rows by `symbol + entry_date`:

| Slice | n | WR | SL | Note |
|---|---:|---:|---:|---|
| RANGE unique base | 65 | 63.08% | 33.85% | not production-grade |
| V109 unique `8-21 or second` | 24 | 75.00% | 25.00% | direction valid, sample unstable |
| `event_to_entry=8` only | 4 | 50.00% | 50.00% | weak boundary; do not keep blindly |
| `9-21` | 20 | 80.00% | 20.00% | better but still small |
| `12-21` | 9 | 100.00% | 0.00% | cleanest but far too small |
| `second-confirm-only` | 2 | 100.00% | 0.00% | insufficient sample |

Conclusion: V110 confirms the semantic direction but **does not promote**. RANGE_TRANSITION still cannot form a stable production rule after dedup. Next research should inspect real structure differences of remaining `WAIT_9_21` / `WAIT_12_21` rows and the generator-level duplicate source; do not tune TP/SL and do not route to production.

## V111 empirical lesson

V111 joined the V110 dedup rows back to V104 strict-reclaim structural indices and compared `WAIT_9_21` vs `WAIT_12_21` by ex-ante structure timing:

| Slice | n | WR | SL | Event→Touch med | Touch→Reclaim med | Stable3/5 | Note |
|---|---:|---:|---:|---:|---:|---:|---|
| WAIT_9_21 | 20 | 80.00% | 20.00% | 7 | 2 | 2/2 | mixed bucket |
| WAIT_9_11 early transition | 11 | 63.64% | 36.36% | 6 | 3 | 0/0 | false-transition bucket |
| WAIT_12_21 mature transition | 9 | 100.00% | 0.00% | 14 | 1 | 0/0 | clean but too small |
| EVENT_TO_TOUCH >= 9 | 9 | 100.00% | 0.00% | 14 | 1 | 0/0 | equivalent to mature wait in current sample |

Remaining `WAIT_9_21` losses were all `WAIT_9_11`, `second_confirm_before_entry=False`, `SL_HIT`, and `event_to_touch=5-7`. The apparent structural difference is not TP/SL: losses come from early RANGE_TRANSITION touches before the transition has matured. `WAIT_12_21` / `event_to_touch>=9` is a valid structure hypothesis, but with only 9 rows and mostly n=1 monthly coverage it remains research-only and must not be promoted.

## V112/V113 generator-level lesson

When expanding beyond V109 accepted rows to the full V104 RANGE_TRANSITION generator output:

| Slice | n | WR | SL | Months | Stable3/5 | Lesson |
|---|---:|---:|---:|---:|---:|---|
| RAW_RANGE_ALL | 238 | 50.84% | 45.38% | 29 | 5/3 | raw rows polluted by duplicates |
| UNIQUE_V110_RANK_ALL | 182 | 52.20% | 44.51% | 29 | 4/2 | RANGE_TRANSITION base weak |
| EVENT_TO_TOUCH>=9 | 18 | 77.78% | 16.67% | 10 | 2/0 | expands V111 but still unstable |
| E2E 12-21 | 18 | 83.33% | 11.11% | 10 | 2/0 | promising, still no stable5 |

Duplicate source: 238 raw RANGE rows collapse to 182 unique `symbol+entry_date`; 54 duplicate groups / 56 extra rows, mostly `CONTINUATION+REVERSAL` double emission. Deduplicate before judging any RANGE_TRANSITION headline metric.

Mature losses (`event_to_touch>=9`) are not caused by TP/SL or pre-reclaim zone-death: all 18 mature rows had zero pre-reclaim closes below `zone_low`. Remaining losers are weak FVG_Demand source semantics: several are continuation FVGs / 100% retrace contexts / weaker ret60 rather than durable demand. Next research should inspect FVG_Demand source construction, not TP/SL.

## V114 FVG_Demand source-construction lesson

V114 reconstructed the three-bar FVG source for the 18 mature rows and separated `FVG_Demand` into source labels using only pre-entry fields:

| Source label | n | WR | SL | Avg | Lesson |
|---|---:|---:|---:|---:|---|
| TRUE_DEMAND_RETEST_CANDIDATE | 9 | 100.0% | 0.0% | +5.99% | non-full-retrace + MidBodyATR>=0.35; clean but small |
| STRONG_IMBALANCE_FULL_RETRACE | 4 | 100.0% | 0.0% | +5.42% | full retrace is not automatically bad if source displacement is strong |
| WEAK_CONTINUATION_FULL_RETRACE_FVG | 4 | 25.0% | 50.0% | -2.21% | main pollution bucket: continuation + full retrace + MidBodyATR<0.65 |
| WEAK_DISPLACEMENT_OTHER | 1 | 0.0% | 100.0% | -7.14% | weak REVERSAL FVG displacement; not durable demand |

Key correction: do **not** reject all `retrace_pct=100` rows. Strong displacement FVGs can survive full retrace. The bad bucket is specifically weak source displacement plus full retrace, especially continuation rows. Next step should apply the same source labels to all unique V104 RANGE_TRANSITION rows to test sample/month stability before any promotion.

## V115 full-sample source-label audit lesson

V115 extended V114 labels to all V104 unique RANGE_TRANSITION rows (238 raw → 182 unique; 18 mature, 164 not mature):

| Source label | n | WR | SL | Avg | Months | Lesson |
|---|---:|---:|---:|---:|---:|---|
| TRUE_DEMAND_RETEST_CANDIDATE | 108 | 56.48% | 40.74% | +0.547% | 25 | best large bucket, but month stability not production-grade |
| STRONG_IMBALANCE_FULL_RETRACE | 40 | 50.0% | 47.5% | -0.279% | 19 | full retrace not globally bad; only keep separate from weak full-retrace |
| WEAK_CONTINUATION_FULL_RETRACE_FVG | 18 | 22.22% | 66.67% | -3.232% | 11 | weak-source pollution survives full-sample expansion |
| WEAK_DISPLACEMENT_OTHER | 16 | 62.5% | 37.5% | +1.664% | 11 | label name is too broad; weak body alone is not enough to reject |

Audit-only counterfactual: excluding `WEAK_CONTINUATION_FULL_RETRACE_FVG` removes 18/182 rows and improves 52.20% WR / 44.51% SL / +0.0899% avg → 55.49% WR / 42.07% SL / +0.4545% avg. This validates the weak-source separation direction, but V115 still does not promote production because TRUE_DEMAND has unstable bad months and the weak bucket has only two n>=3 bad months. Next step should be V116 source-quality-gate simulation only, not production patching or TP/SL tuning.

## V116 source-quality-gate simulation lesson

V116 simulated exactly one source-quality gate, with no TP/SL tuning and no production writes:

`family == CONTINUATION AND retrace_pct >= 95 AND fvg_mid_body_atr < 0.65`

| Scope | Baseline n/WR/SL/Avg | Kept n/WR/SL/Avg | Rejected n/WR/SL/Avg | Lesson |
|---|---|---|---|---|
| V104 unique RANGE_TRANSITION | 182 / 52.20% / 44.51% / +0.0899% | 164 / 55.49% / 42.07% / +0.4545% | 18 / 22.22% / 66.67% / -3.2321% | gate improves base without changing exits |
| Mature E→T>=9 | 18 / 77.78% / 16.67% / +3.3114% | 14 / 92.86% / 7.14% / +4.8895% | 4 / 25.00% / 50.00% / -2.2121% | mature layer materially cleaner |
| Not-mature | 164 / 49.39% / 47.56% / -0.2637% | 150 / 52.00% / 45.33% / +0.0406% | 14 / 21.43% / 71.43% / -3.5236% | removes low-quality early continuation pollution |
| Full-market unique all states | 372 / 56.72% / 40.86% / +0.6533% | 335 / 59.40% / 38.51% / +0.9446% | 37 / 32.43% / 62.16% / -1.9835% | gate direction survives full-market rescan |

Monthly RANGE_TRANSITION result: 29 months, 17 months with n>=3, gate-hit months=11, improved n>=3 months=9, worsened n>=3 months=1. The only worsened n>=3 month was 202507 because the single rejected row was a winner; this is acceptable as simulation evidence but still not production promotion by itself.

Decision: `RESEARCH_ONLY_GATE_DIRECTION_VALIDATED_NOT_PROMOTED`. Use this as a source-quality downgrade/reject candidate in the next research stage, but do not treat it as a global full-retrace ban. Strong full-retrace rows with adequate displacement must remain eligible.

## V117 shadow contract audit lesson

V117 tested whether the V116 gate can move from research metric to production contract. It remained research-only and did not modify production/API/frontend/monitor.

| Scope | Baseline | Kept after gate | Rejected | Delta | Lesson |
|---|---|---|---|---|---|
| RANGE_TRANSITION | 182 / 52.20% WR / +0.0899% avg | 164 / 55.49% WR / +0.4545% avg | 18 / 22.22% WR / -3.2321% avg | WR +3.29pp | valid scoped shadow gate |
| TREND_UP | 190 / 61.05% WR / +1.1930% avg | 171 / 63.16% WR / +1.4145% avg | 19 / 42.11% WR / -0.8006% avg | WR +2.11pp | direction helps but rejected bucket not uniformly toxic |
| ALL unique | 372 / 56.72% WR / +0.6533% avg | 335 / 59.40% WR / +0.9446% avg | 37 / 32.43% WR / -1.9835% avg | WR +2.68pp | broadly useful as downgrade candidate |

Production contract blockers:
- V102 active/candidate picks do **not** carry `fvg_mid_body_atr`; exact gate cannot be computed in production rows yet.
- V104 picks carry `family`/`retrace_pct` but still lack `fvg_mid_body_atr`.
- Strong full-retrace rows remain good enough to keep: full-retrace kept n=89, WR=58.43%, avg=+0.9197%.
- Weak-body-other kept bucket is also good: n=32, WR=68.75%, avg=+2.1306%; therefore do not reject weak body alone.
- T+1 audit passed: same-day exits=0, `exit_idx <= entry_idx`=0.

Decision: `RESEARCH_ONLY_SHADOW_CONTRACT_BLOCKED_FIELD_PROPAGATION_REQUIRED`. Next work must propagate source-quality fields (`family`, `retrace_pct`, `fvg_mid_body_atr`, `source_label`/gate reason) into scanner/pick candidate rows, then run a daily-scan dry-run diff. Do not hard-reject globally; keep RANGE_TRANSITION scoped or shadow/downgrade until field propagation and trend-regime validation are complete.

## V118 daily scanner field-propagation dry-run lesson

V118 propagated the V116 source-quality contract into V90 scanner/candidate rows and ran a full daily-scan dry-run. It remained research-only and did not change production/API/frontend/monitor routing.

| Check | Result | Lesson |
|---|---:|---|
| V90 all candidates | 920 → 920 | identity unchanged; no hard reject |
| V90 recent picks | 49 → 49 | identity unchanged; all remain watch-only in current recent window |
| Required field missing count | 0 for `family/retrace_pct/fvg_mid_body_atr/source_label/v116_gate_reason` | field contract is syntactically ready |
| V116 shadow tags | 505 all / 22 recent | dry-run only; no removal |
| Strong full-retrace guard | V104 TREND_UP strong full-retrace n=60, gate-miskilled=0 | exact V116 condition does not kill strong full-retrace rows |

Critical caveat: V90 currently derives its POI from `DEMAND_OB` / bearish pullback candles, not the same `FVG_Demand` source construction used by V104/V116. Therefore `fvg_mid_body_atr` can be propagated syntactically in V90, but the scanner-level daily dry-run shows a semantic mismatch: most continuation full-retrace rows have negative mid-body ATR because the source candle is bearish OB, not bullish FVG displacement. Treat V118 as field-contract and shadow-diff completion, **not** as production proof for applying the V116 FVG gate to V90. Before production, align the daily scanner source construction to the V104/V116 FVG source or keep this gate scoped to engines that emit true FVG source bars.

## V119 signal supply-chain shortage audit lesson

V119 rebuilt the current scanner supply chain read-only, without changing strategy/API/frontend/watchlist/TP/SL:

| Stage | n | Main loss / lesson |
|---|---:|---|
| scanned bar checks | 3,394,466 | full daily cache path exercised |
| context allowed | 3,380,573 | only 13,893 blocked by broad environment |
| valid SMC events | 343,211 | 198,831 SSL sweep reversal + 144,380 BOS continuation |
| valid POI | 170,962 | 172,174 rejected as `POI_NOT_IN_DISCOUNT` |
| valid reclaim entry | 47,524 | 85,303 broken before reclaim; 38,135 no reclaim in wait |
| V85 candidates | 30,067 | generator emits substantial candidates |
| V86 pass | 933 | main compression: width out of 1.0-1.6 (18,884) and risk out of 1.0-1.5 (10,250) |
| V90 contracts | 920 | 13 RECOVERY substate fails |
| latest per symbol | 791 | per-stock latest candidate set |
| recent 45 trading bars | 49 | 25 reversal + 24 continuation, all WATCH_ONLY |
| active 3 bars | 0 | active window is empty |
| live visible calendar 45d | 7 | frontend live calendar filter further reduces display |

Mechanism conclusions:
- Signal shortage is not caused by absence of raw SMC events; there are 343k valid events and 47.5k reclaim entries.
- The largest loss layer is the V86 contract before V90: tight zone-width/risk gates compress 30,067 V85 rows to 933 pass rows.
- Current tradable active=0 is a time-window effect: V90 keeps 49 recent rows but all are older than the 3-bar active window, so they are WATCH_ONLY.
- Live=7 is a second display-window effect: live uses a calendar 45-day filter while V90 recent uses 45 trading bars.
- POI supply remains collapsed: V90 contracts are 100% `DEMAND_OB`; true FVG source is still absent from daily scanner, so V116 FVG source gate cannot be treated as production semantic proof.
- V102 active=3 and all REVERSAL; V102 candidate pool still contains 193 CONTINUATION + 34 REVERSAL watch rows, showing production whitelist/MTF/5R gates compress continuation heavily.

Audit artifacts: `/root/.hermes/smc_audit/v119_signal_supply_chain_audit_20260619/summary.json` and `report.md`. Decision: `SIGNAL_SUPPLY_CHAIN_SHORTAGE_ROOT_CAUSE_IDENTIFIED_NOT_CHANGED`.

## V120 contract/POI/time/continuation audit lesson

V120 followed the post-V118 diagnosis without changing strategy/API/frontend/watchlist/TP/SL. It audited the four workstreams Lei identified: V86 contract decomposition, parallel POI supply, recent/live time windows, and V102 continuation watch.

Key results:

| Check | Result | Lesson |
|---|---:|---|
| V85 historical candidates | n=23,307 / WR=64.47% / Avg=+0.5595% | raw structure supply exists |
| V86 all conditions pass | n≈530 / WR≈89.8% / Avg≈+2.68% | combined contract is high quality but extremely narrow |
| Zone-width single condition | pass 9,250 WR=66.24%; fail 14,057 WR=63.31% | width alone is not a hard-kill rule |
| Risk single condition | pass 2,061 WR=75.93%; fail 21,246 WR=63.36% | risk helps but must be bucketed |
| Hold-bars single condition | pass 17,383 WR=69.60%; fail 5,924 WR=49.41% | strongest individual quality divider |
| Takeover/T+1 | all current V85 candidates already pass | not the active compression source in this audit |
| POI supply | V85/V86/V90/V102 all 100% `DEMAND_OB` | true `FVG_Demand` and `OB+FVG` are absent as parallel sources |
| Time windows | V90 49 recent trading-bar watch rows → 0 active 3-bar rows → 7 live calendar-45d display rows | recent/watch/tradable/live-display are different layers and must not be mixed |
| V102 continuation watch | n=193 / WR=54.92% / Avg=+2.4227% | do not release all, but do not keep it globally suppressed; split high-quality subfamilies |

Promising continuation watch subfamilies (research-only, not production): RECOVERY + daily DOWN_STRUCTURE + m60 UP_STRUCTURE + risk<=0.8 + width 1.3-1.6 (n=6, WR=83.33%, Avg=+2.73%); RECOVERY + daily DOWN_STRUCTURE + m60 DOWN_STRUCTURE + risk 1.0-1.3 + width 1.3-1.6 (n=7, WR=71.43%, Avg=+4.10%). Samples are small, so they are candidates for next audit only.

Decision: `READ_ONLY_AUDIT_DONE_NO_STRATEGY_CHANGE`. V116 remains shadow-only until the daily scanner emits true FVG source rows; V86 should be decomposed into auditable buckets instead of treated as a monolithic hard kill; parallel POI sources must be restored before any FVG source gate can be production-semantic.

## V121 parallel POI + continuation stability lesson

V121 extended V120 with a read-only parallel-source audit and continuation stability check. No production/API/frontend/watchlist/TP/SL changes were made; V116 stayed shadow-only.

Parallel POI audit around existing `DEMAND_OB` rows:

| Layer | rows | true FVG near event | OB-FVG overlap | FVG reclaim entry | same entry date |
|---|---:|---:|---:|---:|---:|
| V86 | 532 | 153 | 6 | 85 | 3 |
| V90 | 920 | 280 | 100 | 208 | 112 |
| V102 candidate | 227 | 86 | 8 | 0 | 0 |
| V102 continuation | 193 | 76 | 8 | 0 | 0 |

V102 candidate split by nearby true FVG:

| Split | n | WR | Avg | SL |
|---|---:|---:|---:|---:|
| HAS_TRUE_FVG | 86 | 70.93% | +3.4199% | 29.07% |
| NO_TRUE_FVG | 141 | 47.52% | +2.0055% | 52.48% |

Lesson: true FVG context materially improves V102 candidates, but same-entry alignment is zero at V102, so **do not relabel existing OB rows as FVG rows after the fact**. The generator must emit true `FVG_Demand` candidates as a first-class parallel POI source with its own touch/reclaim/entry, then compare to OB rows.

V102 continuation watch stability:
- Overall: n=193 / WR=54.92% / Avg=+2.4227% / SL=45.08%.
- Monthly coverage: only 2 months; stable3=0/2 and stable5=0/2 overall.
- Small promising subfamilies exist but are 2026-only and unstable: e.g. RECOVERY + daily DOWN_STRUCTURE + m60 UP_STRUCTURE + risk<=0.8 + width 1.3-1.6 (n=6, WR=83.33%, Avg=+2.73%, stable5=1/1) and RECOVERY + daily DOWN_STRUCTURE + m60 DOWN_STRUCTURE + risk 1.0-1.3 + width 1.3-1.6 (n=7, WR=71.43%, Avg=+4.10%, stable5=1/1).

Decision: `READ_ONLY_PARALLEL_POI_AND_CONTINUATION_STABILITY_DONE_NO_CHANGE`. Next research should build a shadow-only parallel POI generator (`DEMAND_OB`, `FVG_Demand`, `OB+FVG`) from raw events, dedupe ex-ante, then run month/year stability. Do not promote continuation subfamilies from these small 2026-only samples.

## V122 shadow parallel POI generator lesson

V122 built a read-only first-class parallel POI generator from raw events, emitting separate `DEMAND_OB`, `FVG_Demand`, and `OB+FVG` rows with their own touch/reclaim/entry/T+1 simulation. It did not write V90/V102/watchlist/API/frontend and did not tune TP/SL.

Full-market shadow output after ex-ante dedupe:

| POI source | n | WR | Avg | SL | Lesson |
|---|---:|---:|---:|---:|---|
| DEMAND_OB | 63,947 | 52.37% | -0.1635% | 43.91% | existing OB source is not sufficient without V86-style contract |
| FVG_Demand | 90,378 | 53.41% | -0.0303% | 42.07% | true FVG source alone is abundant but not production-grade |
| OB+FVG | 9,380 | 47.88% | -0.0058% | 50.50% | overlap is not automatically stronger; needs gating |

V86 shadow-contract slice:

| POI source | n | WR | Avg | SL |
|---|---:|---:|---:|---:|
| DEMAND_OB | 799 | 80.23% | +2.3025% | 19.52% |
| FVG_Demand | 410 | 69.76% | +2.0000% | 30.24% |
| OB+FVG | 49 | 73.47% | +3.1343% | 26.53% |

T+1 violations were 0 after dropping rows without a post-entry exit bar. Monthly stability remains weak: DEMAND_OB stable5=6/39, FVG_Demand stable5=8/41, OB+FVG stable5=5/38. Therefore the next gate is not “use FVG instead of OB”; it is **source-specific contract search**. V86-style gates still matter, and `DEMAND_OB` currently remains the strongest broad source under that contract, while `FVG_Demand` and `OB+FVG` are research candidates requiring their own width/risk/hold/source-displacement gates.

Decision: `READ_ONLY_SHADOW_PARALLEL_POI_GENERATOR_DONE_NO_CHANGE`. V116 stays shadow; production promotion requires stable source-specific contracts and field/API/frontend contract closure.

## V123 source-specific contract search lesson

V123 searched separate contracts for the V122 first-class POI sources. It remained read-only: no V90/V102/watchlist/API/frontend writes, no TP/SL tuning, and V116 stayed shadow.

Base V122 rows are weak without contracts: DEMAND_OB 63,947 rows WR 52.37% avg -0.1635%; FVG_Demand 90,378 rows WR 53.41% avg -0.0303%; OB+FVG 9,380 rows WR 47.88% avg -0.0058%.

The headline hold-based search found high-WR shadow slices, but `hold_bars` is an outcome/backtest field and must not be used as a production entry gate. Treat these only as diagnostics of what kind of rows exit quickly, not as deployable scanner logic.

Ex-ante no-hold复核 is the production-relevant view:

| Source | best no-hold contract | n | WR | Avg | SL | Stable5 | Lesson |
|---|---|---:|---:|---:|---:|---:|---|
| DEMAND_OB | risk 0.8-1.5 + width 0.8-1.8 | 2,355 | 70.49% | +1.6923% | 29.13% | 31/37 | strongest deployable-style baseline; still lower than hold-leaked V86 slices |
| FVG_Demand | mid_body_atr>=1.0 + gap_atr>=0.8 + risk 1.0-3.0 + width 1.2-3.0 | 726 | 74.79% | +1.5985% | 24.10% | 23/29 | true FVG needs its own displacement/gap contract; not a relabeled OB row |
| OB+FVG | overlap>=60 + risk 0.8-2.5 + width 0.5-1.6 | 947 | 65.26% | +1.4479% | 34.11% | 22/37 | overlap helps only when high and still has bad months; keep shadow |

Important field-contract gap: V122 persisted CSV lacks `zone_low/zone_high/touch_idx/reclaim_idx/entry_idx`, so V123 could not rigorously search reclaim-strength. Do not invent a proxy. Next reclaim audit must persist those fields and compute reclaim close above zone, reclaim body ATR, and touch-depth before any production claim.

Decision: `READ_ONLY_SOURCE_SPECIFIC_CONTRACT_SEARCH_DONE_NO_CHANGE`. Continuation remains shadow-only; do not globally release continuation or FVG. V116 exact weak-source gate remains shadow until source-specific contracts and API/frontend field contracts close.

## V124 reclaim-strength no-hold FVG_Demand lesson

V124 persisted the missing reclaim geometry fields for first-class `FVG_Demand`: `zone_low`, `zone_high`, `touch_idx`, `reclaim_idx`, `entry_idx`, plus derived ex-ante strength fields: `reclaim_close_above_zone_pct`, `reclaim_body_atr`, `touch_depth_zone_pct`, `touch_to_reclaim_bars`, and `entry_chase_above_zone_pct`. It remained read-only: no production/API/frontend/watchlist writes, no TP/SL tuning, V116 shadow unchanged.

Important methodological correction: V124 uses no-hold dedupe and no-hold contract search. `hold_bars` is not used in ranking or gating because it is an outcome field.

FVG_Demand audit results:

| Slice | n | WR | Avg | SL | Lesson |
|---|---:|---:|---:|---:|---|
| all FVG_Demand no-hold dedup | 90,378 | 53.39% | -0.0344% | 42.08% | raw FVG still weak |
| V123-like no reclaim contract (`mid>=1.0 gap>=0.8 risk1-3 width1.2-3`) | 959 | 62.46% | +0.7804% | 36.60% | displacement/gap alone not enough under no-hold dedupe |
| best broad reclaim score (`mid>=1.0 gap>=0.8 risk1-3 width1.0-2.5 delay1-3 REVERSAL`) | 235 | 71.49% | +0.7536% | 26.81% | improves WR but SL still above target |
| best low-SL reclaim (`mid>=0.65 gap>=0.8 risk1-3 width1.2-2.2 reclaim_above>=0.5 delay1-3 REVERSAL`) | 103 | 79.61% | +0.7557% | 17.48% | strong reclaim close can push SL below V123 24.10%, but sample/coverage too small for production |

Decision: `READ_ONLY_RECLAIM_STRENGTH_NOHOLD_CONTRACT_DONE_NO_CHANGE`. Reclaim strength is a real quality divider for `FVG_Demand`, especially `reclaim_close_above_zone_pct>=0.5` on REVERSAL rows, but the production-grade path is not to promote this immediately. Next step should verify this low-SL reclaim slice by year/month loss anatomy and then wire these fields into the daily scanner contract only as shadow fields first.

## V125 FVG_Demand reclaim loss anatomy lesson

V125 dissected the V124 low-SL `FVG_Demand` reclaim slice by year/month, market state, and remaining losses. It remained read-only: no production/API/frontend/watchlist writes, no TP/SL tuning, V116 unchanged.

Starting V124 low-SL no-hold slice:

`FVG_Demand + REVERSAL + mid_body_atr>=0.65 + gap_atr>=0.8 + risk 1-3 + width 1.2-2.2 + reclaim_close_above_zone_pct>=0.5 + touch_to_reclaim 1-3`

Metrics: n=103, WR=79.61%, avg +0.7557%, SL=17.48%, stable5=9/10, bad5=0. Year split: 2023 n=17 WR=76.47, 2024 n=16 WR=75.00, 2025 n=59 WR=79.66, 2026 n=11 WR=90.91.

Key qualitative change: the remaining FVG pollution is strongly market-state dependent. Keeping only `market_state in (MIXED, BEAR_RISK)` yields n=70, WR=84.29%, avg +1.0030%, SL=14.29%, stable3=11/11, stable5=6/6, bad5=0. This is the first robust source-specific FVG contract that combines displacement/gap/reclaim-strength/market-state without using hold/outcome fields.

High-precision micro shadow slice: same contract plus `risk_pct<=2.5` and `v85_zone_width_pct<=1.8` yields n=24, WR=95.83%, avg +1.0917%, SL=4.17%, but stable5=1/1 only; treat as micro-candidate, not production.

Do not generalize: `DISTRIBUTION`, `ACCUMULATION`, `BULL_CONTINUATION`, and weak `RECOVERY` rows are the pollution bucket; FVG itself is not enough. The next production-oriented step is to carry these reclaim and market-state fields into the daily scanner as shadow contract fields, then audit recent/live coverage before any promotion.

## V126 FVG_Demand reclaim shadow-readiness lesson

V126 tested whether the V125 `FVG_Demand` reclaim contract is ready for scanner shadow integration. It remained read-only: no production/API/frontend/watchlist writes, no TP/SL tuning, V116 unchanged.

Production-relevant contract:

`FVG_Demand + REVERSAL + mid_body_atr>=0.65 + gap_atr>=0.8 + risk_pct 1-3 + v85_zone_width_pct 1.2-2.2 + reclaim_close_above_zone_pct>=0.5 + touch_to_reclaim_bars 1-3 + market_state in (MIXED, BEAR_RISK)`

Metrics: n=70, WR=84.29%, avg +1.0030%, loss_rate=15.71%, hard_exit_rate=11.43%, months=24. Early 2023-2024: n=29, WR=75.86%, avg +0.5754%, hard_exit=20.69%. Late 2025-2026: n=41, WR=90.24%, avg +1.3055%, hard_exit=4.88%. Last 12 months: n=30, WR=93.33%, avg +1.6704%, hard_exit=0.0%.

Critical blocker: recent coverage is zero in the latest 45 trading-day window (latest V124 entry date 20260617; contract n=0 for last 10/20/45 trading days, n=2 for 90 trading days, n=20 for 180 trading days). Therefore the contract is quality-valid historically but **not deployable until daily scanner shadow fields prove real recent candidate coverage**.

Concentration audit: 64 unique symbols, max single-symbol share 2.86%, top5 share 14.29%, HHI 0.0167 — no single-symbol overfit, but adjacent-date repeats exist, so scanner shadow should include per-symbol latest/cooldown dedupe.

Remaining loss anatomy: risk>2.5 covers 63.64% of remaining losses, width>1.8 covers 54.55%, reclaim_close_pos<0.5 covers 36.36%, touch_depth==0 covers 54.55%. These are next shadow refinement fields; do not tune TP/SL.

Required shadow scanner fields: `poi_source`, `combo_family`, `source_mid_body_atr`, `source_gap_atr`, `risk_pct`, `v85_zone_width_pct`, `reclaim_close_above_zone_pct`, `touch_to_reclaim_bars`, `market_state`, `zone_low`, `zone_high`, `touch_idx`, `reclaim_idx`, `entry_idx`.

Decision: `READ_ONLY_FVG_RECLAIM_SHADOW_READINESS_DONE_NO_CHANGE`. Next step is V127: add/carry these fields into daily scanner as shadow-only metadata and verify recent/live coverage; no hard reject or production promotion.

## V127 daily scanner shadow field-contract lesson

V127 patched `v90_daily_full_market_scanner.py` to attach true `FVG_Demand` shadow metadata under `v127_shadow_*` fields while preserving production candidate identity. The scanner still emits the same 920 all candidates and 49 recent picks; no hard reject, no watchlist/API/frontend promotion, no TP/SL tuning.

Implementation boundary:
- Existing V90 rows remain OB-derived scanner rows. Do **not** overwrite `zone_type`/production identity or relabel them as FVG.
- `v127_shadow_poi_source='FVG_Demand'` is emitted only when `fvg_near_event()` finds a true three-bar FVG near the same event and `locate_entry()` confirms its own touch/reclaim/entry. This is not an OB relabel.
- Required shadow fields are prefixed: `v127_shadow_poi_source`, `v127_shadow_combo_family`, `v127_shadow_source_mid_body_atr`, `v127_shadow_source_gap_atr`, `v127_shadow_risk_pct`, `v127_shadow_v85_zone_width_pct`, `v127_shadow_reclaim_close_above_zone_pct`, `v127_shadow_touch_to_reclaim_bars`, `v127_shadow_market_state`, `v127_shadow_zone_low`, `v127_shadow_zone_high`, `v127_shadow_touch_idx`, `v127_shadow_reclaim_idx`, `v127_shadow_entry_idx`.

V127 verification:

| Check | Result |
|---|---:|
| all candidates identity | 920 → 920, same=True, added=0, removed=0 |
| recent picks identity | 49 → 49, same=True, added=0, removed=0 |
| true FVG shadow rows all/recent | 213 / 11 |
| V125 contract pass all/recent | 0 / 0 |
| recent10/20/45 contract pass | 0 / 0 / 0 |
| shadow field missing count | 0 |
| OB relabel violations | 0 |
| T+1 guard violations | 0 |
| production API | unchanged: V102, tradable=0, watch_only=49, live=7 |

Decision: `V127_DAILY_SCANNER_SHADOW_FIELDS_DONE_NO_PRODUCTION_DECISION_CHANGE`. The V125 contract still has no current V90/V86 recent scanner coverage, so production remains blocked. Next step is V128: emit first-class parallel `FVG_Demand` scanner candidates (not merely metadata attached to OB rows), keep them shadow-only, dedupe per symbol/date/source, and re-audit recent/live coverage.

## V128 independent parallel scanner candidate lesson

V128 upgraded daily scanner shadow output from V127's “FVG metadata attached to OB rows” to standalone parallel scanner candidates. It writes separate shadow files only: `v128_parallel_shadow_candidates.json` and `v128_parallel_shadow_recent45.json`; production `v90_all_contract_candidates.json` and `v90_active_picks.json` identities remain unchanged.

Implementation boundary:
- `DEMAND_OB`, `FVG_Demand`, and `OB+FVG` are separate `poi_source` rows.
- Dedupe key is exactly `symbol + entry_date + poi_source`.
- `FVG_Demand` rows are generated from `fvg_near_event()` + their own `locate_entry()`, not by relabeling OB rows.
- `OB+FVG` rows require actual OB/FVG zone overlap and their own entry path.
- V125 contract is `v125_contract_shadow_pass` only; no hard reject and no production promotion.

V128 scanner verification:

| Check | Result |
|---|---:|
| production all candidates | 920 unchanged |
| production recent picks | 49 unchanged |
| parallel raw rows | 40,497 |
| dedup rows | 39,015 |
| recent45 rows | 2,633 |
| by source all | DEMAND_OB 29,109; FVG_Demand 6,815; OB+FVG 3,091 |
| by source recent45 | DEMAND_OB 2,011; FVG_Demand 472; OB+FVG 150 |
| V125 contract pass all/recent45 | 5 / 0 |
| duplicate keys after dedupe | 0 |
| T+1 entry/backtest violations | 0 |
| production API | unchanged: V102, tradable=0, watch_only=49, live=7 |

V128 full semantic shadow backtest over scanner output (audit-only, no TP/SL tuning):

| Slice | n | WR | Avg | Loss | HardExit |
|---|---:|---:|---:|---:|---:|
| ALL | 39,015 | 35.96% | +1.6576% | 64.04% | 57.45% |
| recent45 | 2,633 | 34.22% | +2.4370% | 65.78% | 57.46% |
| V125 contract | 5 | 60.00% | +4.1216% | 40.00% | 40.00% |
| V125 recent45 | 0 | 0 | 0 | 0 | 0 |

By source: DEMAND_OB n=29,109 WR=36.34 Avg=+1.8461; FVG_Demand n=6,815 WR=36.49 Avg=+1.2498; OB+FVG n=3,091 WR=31.22 Avg=+0.7815. The positive avg with low WR indicates a highly skewed payoff distribution; do not interpret this as high signal correctness. The important V128 finding is coverage: independent FVG_Demand supply exists (6,815 all / 472 recent45), but the strict V125 contract still has zero recent45 hits and only five historical scanner hits. Therefore production remains blocked.

Decision: `V128_PARALLEL_SCANNER_SHADOW_DONE_NO_PRODUCTION_DECISION_CHANGE`. Next step should diagnose why V125 is too sparse inside the scanner layer: decompose each V125 clause on independent `FVG_Demand` scanner rows (REVERSAL, mid/gap, risk/width, reclaim strength, delay, market_state), then identify a non-leaky shadow contract with enough recent coverage before any production discussion.

V128 goal验收补充：`v128_goal_result.md` confirmed all requested checks PASS. Top300亏损 anatomy: DEMAND_OB 189 / FVG_Demand 82 / OB+FVG 29；CONTINUATION 239 / REVERSAL 61；risk_pct>3 占 290/300；FVG弱源(mid<0.65或gap<0.8)占 49/300。This means the next filter search should start from risk/width/family/source-quality clause decomposition, not production promotion.

## V129 scanner-layer FVG_Demand contract decomposition lesson

V129 decomposed V125 directly on V128's independent scanner-layer `FVG_Demand` rows. It remained read-only: no production/API/frontend/watchlist writes and no TP/SL tuning.

V125 migration funnel on independent `FVG_Demand` scanner rows:

| Step | all n/WR/Loss | recent45 n/WR/Loss | Lesson |
|---|---:|---:|---|
| base FVG_Demand | 6815 / 36.49% / 63.51% | 472 / 35.59% / 64.41% | raw independent FVG is not production-grade |
| + REVERSAL | 1889 / 43.36% / 56.64% | 159 / 52.83% / 47.17% | family is the strongest first divider |
| + mid>=0.65 | 1428 / 43.77% / 56.23% | 121 / 53.72% / 46.28% | body displacement helps mildly |
| + gap>=0.8 | 315 / 46.03% / 53.97% | 17 / 52.94% / 47.06% | gap clause creates major coverage loss |
| + risk 1-3 | 12 / 58.33% / 41.67% | 0 | V125 risk band is incompatible with current scanner recent layer |
| full V125 | 5 / 60.00% / 40.00% | 0 | too sparse; not deployable |

Why recent45 V125=0: among 472 recent `FVG_Demand` rows, failures are `risk_not_1_3=364`, `gap<0.8=367`, `width_not_1.2_2.2=323`, `not_REVERSAL=313`, `state_not_mixed_bear=261`, while `reclaim<0.5=13` and `delay_not_1_3=1` are not the bottlenecks. Therefore the blocker is not reclaim mechanics but scanner-layer risk/width/gap/family/state distribution.

Scanner-native contract search found only weak research candidates. Best searched slice:
`REVERSAL; mid>=1.0; risk=0-5; width=1.2-4.0; reclaim>=0.5; delay=1-3` gives all n=239 / WR=47.28% / Loss=52.72%, recent45 n=18 / WR=44.44% / Loss=55.56%. This improves raw FVG but remains far below production quality.

Decision: `V129_SCANNER_NATIVE_FVG_CONTRACT_DECOMPOSED_NO_PRODUCTION_CHANGE`. Next research should not loosen V125 into production. It should perform per-loss semantic replay on scanner-layer FVG rows: determine whether high-risk rows are late/chasing entries, zone too wide, reclaim already far above zone, or market-state labeling errors. The bottleneck is now FVG scanner semantics/entry geometry, not supply quantity.

## V130 FVG_Demand loss semantic replay lesson

V130 replayed V128 independent scanner-layer `FVG_Demand` rows with daily K-line context. It remained read-only: no production/API/frontend/watchlist writes and no TP/SL tuning.

Base metrics: all n=6815 / WR=36.49% / Loss=63.51% / hard_exit=54.67%; recent45 n=472 / WR=35.59% / Loss=64.41% / hard_exit=53.39%.

Direct answers:

| Question | Finding | Lesson |
|---|---:|---|
| `risk_pct>3` losses are chase? | loss_n=3081; chase>3 in 57.74%; chase>5 in 29.86%; entry above zone_high median +3.43% | high risk usually means entry is already displaced above the FVG zone, not just a wider stop |
| wide zone invalid? | width>3 loss_n=945; pre-entry close below zone_low only 0.74% | wide zone is not mainly pre-entry zone death; width is dangerous when combined with high risk/chase |
| entry_chase causes buying too high? | chase>3 loss_n=1779; loser 5d MFE median +4.33%, MAE median -6.45% | high-chase rows often still pop briefly but adverse excursion dominates; entry geometry is wrong |
| RECOVERY false recovery? | all n=1637 / WR=23.82% / Loss=76.18%; recent45 n=236 / WR=21.19% / Loss=78.81% | RECOVERY is the main pollution state for scanner-layer FVG |
| BEAR_RISK/MIXED winner-loser difference | all n=2798 / WR=40.39%; recent45 n=211 / WR=49.76% | state helps but is insufficient; winners have stronger early MFE and lower early adverse excursion |

Loss tags show dominant pollution: WEAK_GAP 80.96% of losses, CONTINUATION 75.28%, RECOVERY 28.81%, high-risk/chase layers below them. Therefore the next correction is not source supply or TP/SL; it is FVG entry geometry and state semantics. Do not loosen V125. Next should rebuild scanner FVG entry execution: penalize/reject post-reclaim chase, split/disable false RECOVERY FVG, and require candle-level replay for BEAR_RISK/MIXED before any contract promotion.

Decision: `V130_FVG_DEMAND_LOSS_SEMANTIC_REPLAY_DONE_NO_PRODUCTION_CHANGE`.

## V131 FVG_Demand entry execution shadow lesson

V131 rebuilt scanner-layer `FVG_Demand` entry execution as shadow/backtest only. It tested chase downgrade/reject, RECOVERY split, BEAR_RISK/MIXED candle reaction, and alternative execution models: zone-high limit, zone-mid limit, zone-high+1/+2% second pullback, reclaim-close distance, and entry buffer. It did not change production/API/frontend/watchlist and did not tune TP/SL.

Baseline remained all n=6815 / WR=36.49% / Loss=63.51%; recent45 n=472 / WR=35.59% / Loss=64.41%.

Key findings:

| Test | Result | Lesson |
|---|---:|---|
| reject chase>3 | kept n=4064 / WR=37.28%; rejected n=2751 / WR=35.33% | improves avg/cum but not signal correctness enough |
| reject chase>5 | kept n=5409 / WR=36.99%; rejected n=1406 / WR=34.57% / avg=-0.4595 | chase>5 is toxic but removing it is only a risk-control shadow rule |
| reject chase>8 | rejected n=597 / WR=31.83% / avg=-2.1029 | chase>8 should be downgrade/reject candidate, not full solution |
| RECOVERY split | RECOVERY n=1637 / WR=23.82%; fake_recovery n=685 / WR=23.21%; non_recovery n=5178 / WR=40.50% | RECOVERY must be split out; current label is mostly false recovery for FVG |
| recent not-fake recovery | recent45 not_fake n=331 / WR=41.69% vs RECOVERY WR=21.19% | RECOVERY removal materially improves recent layer but still not production-grade |
| BEAR_RISK/MIXED real reaction | n=2190 / WR=41.51% vs no reaction n=608 / WR=36.35% | real candle reaction helps, but not enough alone |
| limit/second pullback | zone-high wait5 WR=25.83%; zone-mid wait5 WR=19.01%; zone-high+1 wait5 WR=30.80% | naive zone-limit/second-pullback worsens WR and hard exits; catching falling retests is not a solution |
| strict shadow combo | n=2577 / WR=31.78%; recent45 n=165 / WR=38.18% | combining limit+reaction+state still fails; do not promote |

Important correction: The simple idea “buy cheaper inside the zone” failed. It often waits for price to fall back into/near the FVG after reclaim, which selects failed reactions and increases hard exits. Therefore V132 should not promote zone-limit entry. Next work should reframe FVG execution as reaction-quality classification before entry: distinguish takeover impulse from failed reclaim, probably using post-touch/pre-entry candle sequence strength and adverse excursion risk, while keeping all fields ex-ante. Chase>5/8 and RECOVERY can be shadow downgrades, but they are not sufficient production gates.

Decision: `V131_FVG_ENTRY_EXECUTION_SHADOW_BACKTEST_DONE_NO_PRODUCTION_CHANGE`.

## V132 FVG_Demand reclaim takeover / failed-reclaim shadow lesson

V132 tested the next hypothesis after V131: do not buy cheaper inside the FVG; instead classify whether reclaim becomes real takeover or failed reclaim. The script used only ex-ante reclaim/post-reclaim fields: 1-3 bar closes holding above `zone_high`, post-reclaim low pullback depth, reclaim candle body/range, bullish continuation or no break of reclaim low, and entry chase. RECOVERY was kept as a separate bucket. No production/API/frontend/watchlist changes; no TP/SL tuning.

Baseline remained all n=6815 / WR=36.49%; recent45 n=472 / WR=35.59%. RECOVERY stayed toxic: n=1637 / WR=23.82% / Loss=76.18% / HardExit=69.09%.

Key findings:

| Slice | Result | Lesson |
|---|---:|---|
| true_takeover_1_non_recovery | n=1658 / WR=46.20%; recent45 n=63 / WR=53.97% | single-bar hold helps but not enough |
| true_takeover_2_non_recovery | n=1821 / WR=48.98%; recent45 n=68 / WR=57.35% | best broad ex-ante takeover classifier; still not production-grade |
| true_takeover_3_strict_non_recovery | n=956 / WR=57.85%; recent45 n=33 / WR=60.61% | strongest current-baseline selection but coverage small and delayed-entry degrades |
| failed_reclaim_1 | n=912 / WR=32.89% / Loss=67.11% / HardExit=61.84% | immediate failure bucket is real pollution |
| failed_reclaim_3 | n=2100 / WR=25.67% / Loss=74.33% / HardExit=68.29% | second/third-bar failure is the main avoid bucket |
| delayed confirm 1 | n=1658 / WR=40.41%; recent45 WR=38.10% | waiting for confirmation gives up edge |
| delayed confirm 2 | n=1820 / WR=42.36%; recent45 WR=43.28% | confirmation as delayed entry is not the repair |
| delayed confirm 3 strict | n=956 / WR=45.82%; recent45 WR=42.42% | strong-looking current classifier does not survive delayed execution |

Important correction: V132 finds useful diagnostic separation, but not a production entry rule. The takeover features are better as a pre-entry state label / downgrade gate than a delayed-buy trigger. If used later, the classifier must feed a different execution model (e.g. takeover confirmed before existing next-open entry or same-cycle candidate quality scoring), not a 1-3 bar delayed entry after the move has already expanded. Failed-reclaim buckets are valid reject/downgrade candidates; RECOVERY should remain separated from BEAR_RISK/MIXED.

Decision: `V132_FVG_RECLAIM_TAKEOVER_SHADOW_BACKTEST_DONE_NO_PRODUCTION_CHANGE`.

## V133 realtime quality score / failed-reclaim reject gate lesson

V133 followed the V132 conclusion: do not buy cheaper and do not wait 1-3 bars then chase. It tested two separate concepts:

1. **T0 realtime quality score** — only fields known at reclaim close / original next-open entry: non-RECOVERY, REVERSAL family, BEAR_RISK/MIXED state, source displacement/gap, reclaim close above zone, reclaim candle body strength, next-open chase, risk, width, touch→reclaim timing.
2. **Post-reclaim failed gate** — `failed_reclaim_1/3` as cancel/downgrade diagnostics only after those bars close. They must not be used as if known at original next-open entry.

No production/API/frontend/watchlist changes; no TP/SL tuning. T+1 audit passed with 0 `exit_idx <= entry_idx` on original and delayed rows.

Key results:

| Slice | Result | Lesson |
|---|---:|---|
| baseline FVG_Demand | n=6815 / WR=36.49% / HardExit=54.67%; recent45 WR=35.59% | raw scanner FVG remains weak |
| non_RECOVERY | n=5178 / WR=40.50%; recent45 WR=50.00% | RECOVERY isolation helps but insufficient |
| RECOVERY reject | n=1637 / WR=23.82% / HardExit=69.09%; recent45 WR=21.19% | keep as reject/downgrade metadata |
| T0 realtime score ≥10 | n=3798 / WR=40.34%; recent45 WR=47.57% | score improves only modestly |
| T0 realtime score ≥12 | n=1655 / WR=42.48%; recent45 WR=47.66% | stronger score still not production-grade |
| T0 nonREC + REVERSAL + mid>=0.65 + reclaim>=0.5 + chase<=8 | n=1259 / WR=44.80%; recent45 WR=53.70% | best practical T0 slice, still too weak |
| failed_reclaim_3 reject bucket | n=2692 / WR=23.55% / Loss=76.45% / HardExit=70.77%; recent45 WR=26.76% | true pollution bucket, but known only after waiting |
| keep not failed3 + nonREC original-entry outcome | n=3078 / WR=50.62%; recent45 WR=57.81% | diagnostic separation is real, but timing is not original-entry tradable |
| delayed confirm 1/2/3 | WR=40.41% / 42.36% / 45.82%; recent45 WR=38.10% / 43.28% / 42.42% | waiting for confirmation pays lag cost and loses edge |

Important correction: failed-reclaim is a valid **watchlist cancel / downgrade gate**, not a delayed-buy trigger and not an original-entry selector. T0 scoring alone cannot repair FVG_Demand quality. The next real repair must rebuild candidate generation upstream so the system emits a candidate only when takeover quality is already known at decision time (or treats failed-reclaim as cancel metadata for unfilled/watch candidates), rather than buying after the move has expanded.

Decision: `V133_REALTIME_SCORE_AND_FAILED_RECLAIM_GATE_DONE_NO_PRODUCTION_CHANGE`.

## V134 candidate timing lifecycle lesson

V134 implemented the architecture implied by V133: **failed-reclaim is a cancel/downgrade mechanism, not a buy mechanism**. It rebuilt candidate timing as a shadow lifecycle only:

1. `WATCH_AT_RECLAIM_CLOSE`: reclaim close can emit metadata/watch candidate, not BUY.
2. `CANCEL_FAILED_RECLAIM_1/3`: if post-reclaim bars fail, cancel or downgrade unresolved watch candidates.
3. `KEEP_WATCH_TAKEOVER_QUALITY_KNOWN_NO_BUY`: when not failed after 3 bars, takeover quality is known, but this remains watch-only quality metadata; do not chase-buy.

No production/API/frontend/watchlist changes; no TP/SL tuning. T+1 audit passed with 0 `exit_idx <= entry_idx`.

Key results:

| Slice | Result | Lesson |
|---|---:|---|
| baseline all FVG | n=6815 / WR=36.49% / HardExit=54.67%; recent45 WR=35.59% | raw FVG still weak |
| WATCH score10 nonREC at reclaim close | n=3798 / WR=40.34% / HardExit=51.76%; recent45 WR=47.57% | usable watch metadata, not buy signal |
| WATCH strict T0 | n=1257 / WR=44.71% / HardExit=47.57%; recent45 WR=53.70% | best T0 watch label still not production buy |
| CANCEL failed3 from score10 watch | n=1579 / WR=25.97% / Loss=74.03% / HardExit=68.78%; recent45 WR=40.00% | strong cancel/downgrade bucket |
| KEEP not failed3 from score10 watch | n=2219 / WR=50.56% / HardExit=39.66%; recent45 WR=54.72% | diagnostic quality improves after wait, but timing is post-original-entry |
| KEEP not failed3 + strict T0 | n=730 / WR=54.52% / HardExit=36.30%; recent45 WR=60.38% | cleanest lifecycle label, still watch-only because delayed-entry sanity check remains weak |
| delayed confirm 1/2/3 | WR=40.41% / 42.36% / 45.82%; recent45 WR=38.10% / 43.28% / 42.42% | confirms no delayed chase buy |

Coverage is sufficient for shadow lifecycle metadata: score10 nonREC watch rows in last 45 trading dates = 269 rows / 257 symbols; keep-not-failed3 = 188 rows / 184 symbols; cancel-failed3 = 190 rows / 184 symbols. This means the lifecycle model has current coverage as a watch/cancel layer, but **not** as a production entry layer.

Decision: `V134_CANDIDATE_TIMING_LIFECYCLE_SHADOW_DONE_NO_PRODUCTION_CHANGE`. Next safe implementation direction is shadow field propagation/lifecycle display only: emit WATCH at reclaim close, CANCEL on failed reclaim, KEEP_WATCH when takeover quality is known, while keeping tradable BUY disabled until a separate no-lag entry model proves edge.

## V135 lifecycle shadow field export lesson

V135 closed the shadow field-contract layer by exporting lifecycle rows into display/API-ready JSON contracts without touching production scanner/API/frontend/watchlist files. It is still **not a buy model**.

Export contract rules:

1. `v135_display_status`: one of `WATCH`, `CANCEL`, `KEEP_WATCH`, `IGNORE`.
2. `v135_tradable=false` for every row.
3. `v135_failed_reclaim_is_buy_signal=false` for every row.
4. `v135_at_reclaim_action=WATCH_ONLY` only when V134 watch conditions are met.
5. Outcome fields (`pnl_pct`, `exit_reason`, `exit_idx`, `exit_price`, `hold_bars`) are not exported into display contracts.
6. Latest-per-symbol export is deduped by `symbol + poi_source`; duplicates must be 0.

Key artifacts:
- `v135_lifecycle_contract_all.json`: 6815 rows
- `v135_lifecycle_contract_recent45.json`: 472 rows
- `v135_lifecycle_contract_latest_per_symbol.json`: 3503 rows

Validation:

| Check | Result |
|---|---:|
| outcome field leak in export | 0 |
| `v135_tradable=true` | 0 |
| failed-reclaim buy-signal flag true | 0 |
| latest duplicate `symbol+poi_source` | 0 |
| T+1 `exit_idx <= entry_idx` | 0 |
| production summary | unchanged: V102 / trades=195 / WR=87.7 |
| production picks contract | unchanged: tradable=0 / watch_only=49 / raw=49 |

Lifecycle distribution:

| status | all n | latest-per-symbol n | diagnostic WR | Lesson |
|---|---:|---:|---:|---|
| CANCEL | 1579 | 774 | 25.97% | cancel/downgrade only |
| KEEP_WATCH | 2219 | 1082 | 50.56% | quality metadata only, no chase buy |
| IGNORE | 3017 | 1647 | 31.65% | low T0 / RECOVERY pollution |

Coverage remains sufficient for display metadata: recent45 export 472 rows / 434 symbols; latest-per-symbol export 3503 rows / 3503 symbols. This completes field propagation as a **shadow contract**. Next safe step is UI/API dry-run mapping only, or separately research a no-lag entry model. Do not promote `KEEP_WATCH` or failed-reclaim gates into BUY.

Decision: `V135_LIFECYCLE_SHADOW_FIELD_EXPORT_DONE_NO_PRODUCTION_CHANGE`.

## V136-V140 lifecycle display + executable replay lessons

V136-V140 continued from V135 shadow lifecycle exports without production changes:

| Version | Decision | Key lesson |
|---|---|---|
| V136 | UI/API dry-run mapping only | lifecycle rows can be mapped for display, but `tradable=false`; display readiness is not buy readiness |
| V138 | executable semantic audit | only `RECLAIM_NEXT_OPEN` is executable; delayed T2/T3 confirmation loses edge; `market_state != MIXED` gives the best non-production executable slice |
| V139 | semantic hardening | `RECLAIM_NEXT_OPEN + market_state != MIXED` is the current best shadow slice: n=273, WR=80.22%, Avg=+2.998%, recent45 n=30, T+1=0. Further hardening (`entry_chase<=2`, `t0score>=8`, `risk<=6`, reclaim body filters) shrinks coverage without improving average PnL. Remaining losses concentrate in `ZONE_CLOSE_DEAD_T1`, so the next question is K-line failure semantics, not TP/SL tuning |
| V140 | K-line semantic replay of ZONE_CLOSE_DEAD | Among 43 `ZONE_CLOSE_DEAD_T1` losses, 36/43 (83.72%) have an ex-post lead signature: no entry-day follow-through <=1% (27/43), entry above zone >2% (22/43), or entry-day zone retest (3/43). Counterfactual diagnostic on the full non-MIXED reclaim baseline: baseline n=273/WR=80.22/Avg=+2.998%; keeping rows without the V140 lead signature gives n=75/WR=88.00/Avg=+4.1215/recent45 WR=81.82. However, V140 lead signature is not automatically production tradable because much of it is known on/after entry-day close. It can only become a watch/cancel or next-cycle downgrade signal after a timing audit proves availability before action. |

V140 artifacts: `/root/.hermes/scripts/v25/v140_zone_close_dead_kline_semantic_replay.py`, `/root/.hermes/smc_audit/v140_zone_close_dead_kline_semantic_replay_20260621/report.md`, `summary.json`, `v140_zone_close_dead_replay_rows.csv`, `v140_lead_signal_counterfactual.csv`.

Decision: `V140_READONLY_ZONE_CLOSE_DEAD_KLINE_REPLAY_DONE_NO_PRODUCTION_CHANGE`. Next step should audit whether V140's no-follow-through / entry-above-zone / zone-retest signatures are known early enough to cancel a watch candidate before a buy, or only after entry. Do not promote as an original-entry selector.

## V141 timing availability audit lesson

V141 audited whether V140's lead signatures are available early enough to cancel the original `RECLAIM_NEXT_OPEN` buy. It remained read-only: no production/API/frontend/watchlist writes and no TP/SL tuning.

Key timing result:

| Signal | Earliest availability | n | WR | Avg | Lesson |
|---|---|---:|---:|---:|---|
| `entry_above_zone>2` | before next-open buy | 146 | 80.82% | +2.9276% | buy-time known, but filtering it does not improve the baseline |
| `entry_day_retests_zone` | after buy/open intraday | 21 | 80.95% | +4.5303% | cannot avoid original buy; not a reject rule |
| `no_entry_follow_through<=1%` | entry-day close | 126 | 71.43% | +1.7565% | useful downgrade metadata only after original buy timing has passed |
| no V140 lead | no failure signature | 62 | 87.10% | +3.7101% | cleanest diagnostic slice, but mostly depends on late-known components |

Counterfactual on V139 no-MIXED reclaim baseline: baseline n=273 / WR=80.22% / Avg=+2.9981. Rejecting only buy-time-known entry-gap rows leaves n=127 / WR=79.53% / Avg=+3.0791 — no meaningful improvement. Keeping rows without any V140 lead signal gives n=62 / WR=87.10% / Avg=+3.7101, but that uses entry-day-close/intraday information and is not an original-entry selector.

ZONE_CLOSE_DEAD_T1 timing split: 22/43 are buy-time-known `PRE_BUY_AT_NEXT_OPEN`, 12/43 are `ENTRY_DAY_CLOSE`, 2/43 are `ENTRY_DAY_AFTER_OPEN`, 7/43 have no V140 lead. Therefore V140 lead signatures are valid lifecycle/watch/cancel diagnostics, but **cannot be promoted as a combined no-lag buy filter**.

Decision: `V141_READONLY_V140_LEAD_TIMING_AVAILABILITY_DONE_NO_PRODUCTION_CHANGE`. Next safe work: either audit the buy-time-known entry-gap/chase component alone as a no-lag filter, or export late-known components as watch/cancel lifecycle metadata only; do not turn them into BUY.

## V148 readonly lifecycle API/display contract lesson

V148 is the correct next step after V147 when V144 preview payload already passes K-line integrity replay: expose the replay result as an explicit read-only API contract, not as production signal logic. The only code change was in `/api/v144-dry-run-preview`: add a `contract` block with `shadow_only=true`, `display_only=true`, `production_write=false`, `buy_enabled=false`, `trade_action=NO_BUY`, row counts, status counts, bad-buy count, and V147 mismatch/missing-kline summary. The existing `/v144-preview` page was verified to consume only this preview API and not `/api/picks` or `/api/live-prices`.

V148 acceptance checks:

| Scope | Rows | bad_buy_like | V147 mismatch | V147 missing kline | Pass |
|---|---:|---:|---:|---:|---|
| latest_per_symbol | 265 | 0 | 0 | 0 | yes |
| recent45 | 30 | 0 | 0 | 0 | yes |
| all | 273 | 0 | 0 | 0 | yes |

Production isolation must still be probed after restart: `/api/summary` remains `V102_BALANCED_VOLUME_GATE` with 195 trades and 87.7% WR; `/api/picks/contract` remains tradable=0/watch_only=49/raw=49; `/api/picks` remains 49 rows; `/api/live-prices` remains 5 picks; leak marker count for V144/V148/NO_BUY markers is 0 on production endpoints.

Browser smoke for `/v144-preview` should verify meta `scope=latest_per_symbol | rows=265 | BUY-like=0`, table rows display `NO_BUY`, and summary counts 51 cancel / 60 keep-watch / 12 intraday-risk-note / 142 pre-buy-gap-note. This proves the display contract, not promotion.

Decision: `V148_READONLY_LIFECYCLE_CONTRACT_DONE_NO_PRODUCTION_CHANGE`. The V144/V147/V148 lifecycle layer remains `shadow-only / display-only / NO_BUY`; it cannot feed production picks, morning push, auto-buy, or tradable watchlist without a separate full-market production promotion audit.

## V147 V144 preview integrity replay lesson

V147 performed a read-only K-line integrity replay against the V144 independent preview payload after V146 connected `/v144-preview`. It did not change production/API/frontend/watchlist/TP/SL; it only wrote audit artifacts under `/root/.hermes/smc_audit/v147_v144_preview_integrity_replay_20260621/`.

Validation scope:

| Scope | rows | missing kline | bad_buy_like | mismatch |
|---|---:|---:|---:|---:|
| all | 273 | 0 | 0 | 0 |
| recent45 | 30 | 0 | 0 | 0 |
| latest_per_symbol | 265 | 0 | 0 | 0 |

Status distributions matched the V144 payload exactly: all=52 cancel / 62 keep-watch / 13 intraday-risk-note / 146 pre-buy-gap-note; recent45=6 / 10 / 1 / 13; latest=51 / 60 / 12 / 142. Recomputed K-line fields (`entry_above_zone`, `entry_above_reclaim`, entry-day retest, entry-day close below zone, early zone fail, no follow-through) all matched payload fields within tolerance.

Production isolation was also verified: `/api/summary` stayed `V102_BALANCED_VOLUME_GATE` with 195 trades and 87.7% WR; `/api/picks/contract` stayed tradable=0/watch_only=49/raw=49; `/api/picks` stayed 49 rows; `/api/live-prices` returned 5 picks. Leak marker count for V144/V143 lifecycle markers and `NO_BUY` was 0 across production endpoints.

Decision: `V147_V144_PREVIEW_INTEGRITY_REPLAY_DONE_NO_PRODUCTION_CHANGE`. V144 preview remains display-only / NO_BUY; K-line replay consistency is a UI contract validation, not a production signal promotion.

## V149-V150 lifecycle exit tradeoff lesson

V149/V150 tested whether late-known lifecycle metadata from V140-V148 can become executable position management. Both remained read-only: no production/API/frontend/watchlist writes and no TP/SL tuning. A-share T+1 was enforced by shifting entry-day close / intraday lifecycle exits to the next trading-day open; same-day exit violations were 0.

V149 result:

| Variant | n | WR | Avg | Recent WR | Lesson |
|---|---:|---:|---:|---:|---|
| BASELINE_V138_RECLAIM_NEXT_OPEN | 273 | 80.22% | +2.9981% | 76.67% | current shadow baseline |
| ENTRY_CLOSE_CANCEL_T1_OPEN | 273 | 81.68% | +2.8154% | 83.33% | WR improves but average falls |
| CANCEL_OR_INTRADAY_RISK_T1_OPEN | 273 | 82.05% | +2.6882% | 83.33% | WR improves more, average falls more |
| CANCEL_AND_PREBUY_GAP_NO_ENTRY | 127 | 82.68% | +2.6864% | 88.24% | coverage shrinks; average still below matched baseline |

Release gate failed because avg improvement and hard-exit reduction did not pass. V150 paired every lifecycle variant against the same baseline trades and found the root cause: lifecycle exits truncate winners more often than they rescue losers.

| Variant | Avg delta vs baseline | Changed n | Helped | Hurt | Rescued losers | Hurt winners | Changed avg delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| ENTRY_CLOSE_CANCEL_T1_OPEN | -0.1827 | 48 | 17 | 31 | 17 | 31 | -1.0390 |
| CANCEL_OR_INTRADAY_RISK_T1_OPEN | -0.3099 | 55 | 19 | 36 | 18 | 36 | -1.5381 |
| CANCEL_AND_PREBUY_GAP_NO_ENTRY | -0.3927 | 48 | 17 | 31 | 17 | 31 | -1.0390 |

Decision: `V150_LIFECYCLE_EXIT_TRADEOFF_DIAGNOSED_NO_PROMOTION`. Do not promote lifecycle exit to production SELL even when WR rises. Keep it as risk/watch metadata unless a timing-aware subrule proves positive matched average delta, positive changed-trade delta, and rescued losers >= hurt winners under strict T+1.

## Pitfalls

- Do not report raw rows when duplicate family rows inflate `n` and WR.
- Do not keep `event_to_entry=8` as a boundary without isolating it; in V110 it was the weak edge.
- Do not treat `12-21` as production-ready solely because it is clean; sample and monthly coverage are too small.
- Do not use this operational/research audit as Pine/LuxAlgo semantic correctness proof; signal derivation still requires separate semantic re-derivation audits.

# V316-V319 V185 continuation closure

Session date: 2026-07-08

Use when continuing V185 production research after V315, especially if the user says “继续” and expects no repeated scalar mining.

## Fixed production-improvement gate used in V316-V319

| Gate | Threshold |
|---|---:|
| n | >=300 |
| min_year_n | >=40 |
| net WR (`pnl_pct>=0.8%`) | >=87% |
| AvgPnL | >=6.8% |
| all_year_WR_min | >=84% |
| micro_profit_pct | <=1% |
| T+1 violations | 0 |

## V316 exit-mechanism frontier

Artifact: `/root/.hermes/smc_audit/v316_v185_exit_mechanism_frontier_latest.json`

Result:

| Item | Value |
|---|---:|
| V185 baseline | n=334 / net WR=85.6287 / avg=6.5628 / year min=81.25 |
| exit configs tested | 152 |
| production pass | 0 |
| best exit-only | FULL_TP1.0R_H10 |
| best metrics | n=334 / WR=90.1198 / avg=4.6041 / year min=87.5 |

Conclusion: exit-only can raise WR but destroys average PnL. Do not promote an exit-only fast-TP overlay unless a later independent signal layer restores AvgPnL.

V185 residual loss buckets:

| Bucket | n |
|---|---:|
| DIRECT_STOP__ENTRY_OR_SIGNAL_QUALITY_PROBLEM | 22 |
| MFE_0P5_TO_1R_THEN_TIME_LOSS__WEAK_FOLLOW_THROUGH | 9 |
| OTHER_RESIDUAL_LOSS | 9 |
| MFE_GE_1R_THEN_TIME_LOSS__EXIT_GIVEBACK_PROBLEM | 6 |

## V317 dynamic exit overlay

Artifact: `/root/.hermes/smc_audit/v317_v185_dynamic_exit_overlay_latest.json`

Result:

| Item | Value |
|---|---:|
| safe pre-entry features | 49 |
| single rules | 905 |
| pair rules | 2472 |
| production pass | 0 |
| best policy | `pre_range_20d_pct>=17.219049` selects 218 rows for fast TP1R |
| best metrics | n=334 / WR=89.521 / avg=5.5024 / year min=84.375 |

Conclusion: pre-entry selected fast exits still cannot preserve V185 average. Close this branch.

## V318 broader V167 candidate-supply frontier

Artifact: `/root/.hermes/smc_audit/v318_v167_candidate_supply_frontier_latest.json`

Purpose: change information content by starting from broader V167 scanner-time source (793 trades), not just filtering V185.

Result:

| Scope | Result |
|---|---:|
| source rows | 793 |
| safe features | 49 |
| single results | 6036 |
| pair results | 4572 |
| production pass | 0 |
| best policy | `entry_above_zone_high_raw_pct<=1.681503 AND target_room_prior5_high_pct>=0.747664` + FULL_TP1.0R_H10 |
| best metrics | n=301 / WR=94.3522 / avg=3.1675 / min_year_n=29 |

Conclusion: broader daily candidate supply can create very high WR pockets, but only by using 1R exits with low average and/or year coverage collapse. No promotion over V185.

## V319 60min feasibility audit

Artifact: `/root/.hermes/smc_audit/v319_m60_feasibility_latest.json`

Purpose: verify whether the next required information source (60min entry/SL/RR refinement) is available locally for full 2023-2026 validation.

Result:

| Dataset | Rows | entry-date hit | hit % | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|
| V185 | 334 | 35 | 10.48% | 0% | 0% | 20.19% | 34.15% |
| V167 | 793 | 145 | 18.28% | 0% | 0% | 36.84% | 58.75% |

Local 60min cache range is only about `20251020/20251023` to `20260515` for relevant symbols. It cannot support full 2023-2026 promotion validation.

Conclusion: do not claim M60 promotion from current local cache. M60 can only be used for recent smoke diagnostics unless complete historical intraday data is acquired or reconstructed.

## Closed branches

Do not keep re-running these without new data/information content:

1. V185 daily pre-entry scalar gates (V315).
2. V185 exit-only matrix (V316).
3. V185 dynamic fast-exit overlay selected by pre-entry features (V317).
4. V167 broader daily scanner supply + simple gates/exit configs (V318).
5. Full-history M60 entry refinement using current local cache (V319) — insufficient coverage.

## Valid next direction

V185 remains production baseline. A true next improvement requires one of:

1. complete historical intraday data for 2023-2026, then build MTF entry/SL/RR matrix;
2. genuinely new scanner-time signal supply, not historical V185/V167 scalar filtering;
3. production/live hardening around V185 while no better candidate passes the fixed gate.

## Update: V360–V395 frontier closure (2026-07-12)

The formerly proposed “complete historical intraday data” direction was completed using full-history Sina 60min data. V382 verified source coverage, raw-daily reconstruction, independent semantics, causal MTF timing, serial execution, and T+1; the fixed MTF replay still failed economically (n=4,832, WR=35.3891%, AvgPnL=-0.1562%, minimum-year WR=32.04%). The daily canonical continuation branch also failed in V360 (n=13,761, WR=69.38%, AvgPnL=0.2872%).

Subsequent independent PIT layers were tested and closed: same-day cross-sectional participation (V382/V383), prior-20-session behavior cohorts (V384/V385), exact disclosure-time announcements (V386–V392), prior-day 龙虎榜 data (V393/V394), and prior-completed-session exchange financing/margin buy intensity (V395). V395 had 100% date coverage (788/788), strict pre-hold dates and 4,832 fixed V381 rows, but no state passed the predeclared discovery gate: high financing intensity worsened to WR=32.73%/AvgPnL=-0.4010%; low intensity was only WR=37.48%/AvgPnL=0.0093%; non-margin-eligible was WR=36.54%/AvgPnL=-0.0256%. None met n>=300, each year>=40, WR uplift>=5pp, AvgPnL uplift>=1pp, and minimum-year WR uplift>=3pp simultaneously.

**Do not resume scalar/threshold/exit mining on these sources.** Financing/margin is now a closed branch. The first main-flow feasibility check (V396) also failed before replay: Eastmoney/AkShare individual and market fund-flow endpoints each expose only 120 recent rows (2026-01-09 to 2026-07-10 in two independent equity samples and the market series), with no verifiable PIT publication timestamp. It is therefore **not** a closed economic result but an unavailable source; do not run an outcome replay or infer 2023–2026 performance from it. The only eligible new direction is an untested data class with full point-in-time history (e.g. order book/tick, verified institutional holdings, ETF creations/redemptions, or a provider exposing main-flow history with timestamps), which must first pass full coverage, publication-time/PIT, price-alignment, and full-market completeness gates before any outcome replay.

## V397 aggregate fund-holdings feasibility gate (2026-07-12)

Artifact: `/root/.hermes/smc_audit/v397_pit_fund_holdings_availability_latest.json`

Eastmoney aggregate `基金持仓` snapshots are materially better than the main-flow endpoint on raw history: all 15 required 2022Q3–2026Q1 snapshots fetched successfully, and they map conservatively to **100% (4,832/4,832)** fixed V381 hold identities while using a report-period watermark strictly before each hold. No outcome field is read.

This source **does not pass** the strict PIT gate: its aggregate endpoint provides no verifiable per-snapshot publication timestamp. A statutory reporting-deadline watermark is only a conservative theoretical upper bound; it does not prove when this provider's aggregate snapshot was observable. Therefore `outcome_replay_allowed=false`, no threshold search or outcome replay was run, and the branch is closed under the existing evidence standard.

Current result: all free, locally available historical source classes have now either failed their predeclared information gate (OHLCV/MTF, participation, cohorts, disclosures, 龙虎榜, margin) or failed the strict source-PIT availability gate (main flow, aggregate fund holdings). A next run requires a source with **verifiable raw publication timestamps or full historical order-book/tick coverage**, not another filter on the existing data.

## V404–V405 strict-prior-date block-trade branch (2026-07-12)

A new source class was tested without same-day publication ambiguity: Eastmoney A-share block trades are used only when `TRADE_DATE < completed V381 hold_time date` (30-calendar-day source window). V404 fetched all 115,734 source records across 24 verified pages for 2023–2026, accounted for all 4,832 frozen V381 identities, had zero query failures, and never read outcomes before the availability decision. It passed PIT availability.

V405 then ran exactly four predeclared categorical states—`NO_BLOCK`, `INSTITUTION_NET_BUY`, `INSTITUTION_NET_SELL`, and `NON_INSTITUTION_BLOCK`—with no threshold/combination/exit search. No state passed the discovery gate (`n>=300`, each year `>=40`, WR uplift `>=5pp`, AvgPnL uplift `>=1pp`, min-year WR uplift `>=3pp`, both chronological epochs materially positive). The closest supported state, `NON_INSTITUTION_BLOCK`, was n=413 / WR=36.56% / AvgPnL=-0.20%, only +1.17pp WR and -0.04pp AvgPnL versus n=4,832 baseline (WR=35.39%, AvgPnL=-0.16%). Institution-net-buy was materially worse: n=151 / WR=29.14% / AvgPnL=-1.31%.

**Close block-trade context as an economic branch.** It is a valid PIT source but adds no usable predictive information for the fixed V381 MTF execution. Artifacts: `v404_pit_block_trade_availability_latest.json`, `v405_pit_block_trade_frozen_outcome_replay_latest.json`.

## Correction: V399–V403 PIT top-shareholder branch (2026-07-12)

The first V399 result (60.55% coverage) was **not a valid source-availability failure**: its announcement-metadata requests had transient JSON/anti-bot failures. V400 reproduced a 100/100 recovery pilot. Rerunning V399 with four workers and bounded retry correctly produced 3,020/3,020 metadata success, 4,807/4,832 PIT-ready identities (99.48%), and every year above 99.26%. Thus Eastmoney public report metadata plus the report-period Top-10 shareholder endpoint is a valid PIT data source under the strict rule `report_end < entry_date` and `notice_date < entry_date`; no same-day use.

V402 materialized all 4,807 ready identities / 4,517 unique snapshots with zero request failures, before outcomes were opened. The immutable feature schema was: Top-10 concentration >=50%, top-1 holder >=30%, fund present, institutional holder present, and Hong Kong Central Clearing nominee present.

V403 then ran the only allowed frozen outcome replay against fixed V381 identities. The matched baseline was n=4,807, WR=35.47%, AvgPnL=-0.1480%, min-year WR=32.11%. No feature state passed the predeclared discovery gate (n>=300; each year>=40; WR uplift>=5pp; AvgPnL uplift>=1pp; min-year WR uplift>=3pp; both 2023–24 and 2025–26 chronological epochs must retain positive material uplift). The closest descriptive state, `institutional_present=false`, was n=793/WR=39.34%/AvgPnL=0.3411%, but it failed fixed uplift and 2026 support gates. **Close top-shareholder snapshot features as an economic signal branch; do not threshold-mine it.**

Artifacts: `v399_pit_shareholder_holdings_feasibility_latest.json`, `v402_pit_shareholder_feature_materialization_latest.json`, `v403_pit_shareholder_frozen_outcome_replay_latest.json`.

## V406–V407 northbound and tick source-availability closure (2026-07-13)

Two final free-source probes were tested **without opening outcomes**:

- **V406 Northbound holdings:** strict prior-date, 30-calendar-day queries over all 4,832 V381 hold identities. The endpoint was not complete: 4,471 rows produced `NULL_RESULT` or pagination failures. Although returned rows were prior-date-safe, query completeness failed, so no replay was permitted. Artifact: `v406_pit_northbound_holdings_availability_latest.json`.
- **V407 mootdx historical transaction/tick:** six fixed 2023–2025 probes across 000001.SZ and 600519.SH. Within each symbol, three distinct requested historical dates returned byte-identical transaction payloads; zero of six final transaction prices matched the corresponding historical daily close. The endpoint therefore serves a current/stale snapshot, not date-addressable historical ticks. Artifact: `v407_pit_tick_history_availability_latest.json`.

**Close both as unavailable source branches.** They are not economic failures, and must not be converted into outcome replays, proxy features, or threshold searches.

At this point every accessible free historical source is either economically closed under a frozen causal replay, or unavailable under full PIT/coverage checks. The only legitimate qualitative next step is obtaining a provider/archive with verifiable, date-addressable historical order-book/tick data or another previously untested source with raw publication timestamps. Any candidate must pass, in order: full V381 identity coverage; strict prior-time/PIT audit; raw source-to-price alignment; then one frozen-schema outcome replay. Do not resume existing-data scalar/exit/threshold mining.

## V420–V516 local pure-structure frontier closure (2026-07-15)

After external-data work was abandoned, the local OHLCV program tested genuinely distinct daily, cross-security, weekly-transfer, and hierarchical SMC ontologies using outcome-blind generation, independent semantic oracles, one frozen serial strict-T+1 replay, and independent metric recomputation. The final registry artifact is `/root/.hermes/smc_audit/v516_local_structure_frontier_closure_latest.json`.

No ontology passed all-year promotion. Frontier examples: internal inducement sweep had the highest gross WR (74.3983%) but AvgNet only 0.0744%, payoff 0.4436, PF 1.0414 and negative 2023/2024; weekly SSL rejection-block transfer had the highest AvgNet/payoff (0.5351%, 0.9479) but negative 2023/2026; weekly breaker transfer was n=50,605 / WR=68.1889% / AvgNet=0.3668% / payoff=0.5641 / PF=1.1224 and negative 2023/2026. Weekly SSL→CHOCH→demand, weekly IFVG support, weekly BOS-context→daily SSL, monthly BOS→weekly FVG, and weekly two-sided purge were also closed by economic or pre-outcome support gates.

The correct weekly-breaker replay artifact is `v500_weekly_breaker_daily_transfer_frozen_t1_replay_latest.json`; it enforces one open setup per symbol and suppresses 15,767 overlapping entries. Do not replace it with a non-serial replay.

Program decision: `CURRENT_LOCAL_OHLCV_PURE_STRUCTURE_RESEARCH_COMPLETE__ZERO_ALL_YEAR_PROMOTION_PASS__STOP_STRATEGY_ITERATION`. Do not continue with timeframe, threshold, context, SL, TP, hold-period, year, or regime variants. Restart only for a causally distinct ontology that first produces n>=300 and every 2023–2026 year n>=40 without opening outcomes.

## V444–V446 local pure-structure frontier (2026-07-14)

After V443 closed Supply-Failure Breaker, Target-First DOL, and Protected-Swing Transfer, three additional predeclared daily ontologies were tested over 4,903 symbols with unchanged strict-T+1 execution and no parameter/exit search:

- `INTERNAL_LIQUIDITY_TRANSFER`: external HH/HL → confirmed internal high/HL → internal-low sweep while external low holds → internal-high displacement → next open. Result: n=4,243, WR=70.12%, AvgPnL=+0.2985%, payoff=0.4655, PF=1.0922. It failed because 2023/2024 AvgPnL were -1.6187%/-0.7201%.
- `BEAR_IFVG_ROLE_REVERSAL`: bearish FVG → close invalidates above gap → later retest/reclaim/hold → next open. Result: n=88,835, WR=60.71%, AvgPnL=+0.3469%, payoff=0.7427, PF=1.1477. 2023 remained negative.
- `SSL_CREATED_BEAR_IFVG_ROLE_REVERSAL`: a confirmed 3/3 SSL must be raided by the bearish-FVG creation leg before the same IFVG lifecycle. Result: n=50,401, WR=60.73%, AvgPnL=+0.5034%, payoff=0.7863, PF=1.2158. This improved the generic IFVG branch but still failed annual stability: 2023 WR=48.49%/Avg=-0.1230%, 2026 Avg=+0.1206%.

V445 independently rederived 96,238 semantic seeds and checked 93,078 frozen trades against raw bars: zero geometry, chronology, duplicate, SL, PnL, or T+1 failures. Therefore the failure is economic/year-regime instability, not causality or execution contamination. Do not reopen these branches by deleting years or tuning SL/TP/hold/thresholds. Artifacts: `v444_internal_liquidity_ifvg_frontier_latest.json`, `v445_v444_independent_integrity_latest.json`, `v446_ssl_created_ifvg_reversal_latest.json`.

## V408 Eastmoney 5/15/30-minute availability closure (2026-07-13)

Artifact: `/root/.hermes/smc_audit/v408_eastmoney_intraday_history_availability_latest.json`.

A frozen, no-outcome probe used only V381 `symbol` and `hold_time`: three identities in each of 2023–2026 (12 identities), exact-date requests across 5/15/30-minute bars (36 requests). The predeclared gate required every historical date to return bars before any replay.

Result: only 6/36 requests returned any bars; 26 returned zero bars and 4 had bounded-retry query failures. No 2023–2025 probe returned data; the few returns were recent 2026 dates. Therefore the endpoint is a limited recent intraday window, not full-history data. `availability_gate_pass=false`, `outcome_replay_allowed=false`; no PnL/exit/outcome fields were read. Close this source and do not infer performance from its recent fragment.

## V414 external-source restart qualification (2026-07-13)

Artifact: `/root/.hermes/smc_audit/v414_external_source_restart_qualification_latest.json`.

V413 had already verified 17/17 free/local branches closed (10 source-valid economic failures, 7 unavailable), so the next step was a **source-restart qualification**, not another replay. No price, entry, exit, PnL, or outcome field was opened.

Direct documentation checks established two conditional candidates:

- **JQData:** its documentation lists 1m/5m/15m/30m/60m/120m bars, says minute history is 2005-present, and lists institutional stock ticks from 2010-01-01. This is the highest-ranked candidate because timestamped tick records can represent a genuinely new intraday information class for 2023–2026.
- **Tushare Pro:** its documentation exposes date-range `pro_bar(...freq='1min')` and says minute data need separate entitlement. It is conditionally eligible, but coverage and entitlement remain unproven.

The current environment has neither `jqdatasdk` nor `tushare` installed and no matching credentials, so neither provider can be queried honestly. The next allowed probe after authenticated access is supplied is fixed and outcome-free: 12 frozen V381 identities (three each year, 2023–2026) at exact dates; then all 4,832 V381 identities for coverage, timestamp causality, and daily-price alignment. Only then is one frozen-schema replay allowed.

**Program state at V414:** `EXISTING_DATA_RESEARCH_COMPLETE__EXTERNAL_AUTHENTICATED_SOURCE_REQUIRED_FOR_ANY_LEGITIMATE_RESTART`. The user later explicitly abandoned unavailable external-data dependencies, so subsequent work may test genuinely new local pure-structure ontologies, but must not reopen any listed scalar/threshold/exit/source branch.

## V506–V510 higher-timeframe local pure-structure continuation (2026-07-15)

Two new ontologies were tested without production/frontend/watchlist writes:

1. **V506 monthly BOS → weekly FVG → daily transfer.** The outcome-blind generator scanned 4,897 symbols and produced 12,981 semantic seeds with zero order failures, but only 5 seeds in 2023 because the 750-day cache cannot warm up a 2-left/2-right monthly pivot/BOS state early enough. It failed the frozen support gate (`each year n>=40`), so no oracle outcome replay was opened. Close this ontology under the current cache horizon; do not lower the yearly gate.
2. **V507–V510 weekly bearish FVG inversion support.** Contract: completed weekly bearish FVG → first later weekly close above its upper edge by 0.3% → post-inversion daily touch → later reclaim → later hold → next-open entry; SL below IFVG, nearest already-visible weekly swing-high target, time30, fee 0.2%, serial strict T+1. V507 produced 30,039 seeds across all years; V508 independently rederived all 30,039 with zero mismatch and no outcome headers. V509 replay closed 27,827 rows: gross WR 58.9607%, net>=0.8 WR 50.8068%, AvgNet +0.1387%, payoff 0.7601, PF 1.0433, SL 37.7906%, T+1=0. Year 2023 AvgNet -0.8472%/WR 37.7217%; 2026 AvgNet -0.4593%. V510 independently matched every metric and found zero chronology, duplicate, T+1, or serial-overlap failures.

**Decision:** weekly IFVG improves headline WR versus the plain weekly bullish-FVG transfer by +2.2579pp, but worsens AvgNet by 0.1992pp, payoff by 0.1096, and PF by 0.0542; it fails all-year economics and is closed. Do not tune inversion threshold, lifecycle window, SL, TP, hold, year, or regime. Artifacts: `v506_monthly_bos_weekly_fvg_transfer_latest.json`, `v507_weekly_ifvg_support_transfer_latest.json`, `v508_weekly_ifvg_support_oracle_latest.json`, `v509_weekly_ifvg_support_frozen_t1_replay_latest.json`, `v510_weekly_ifvg_support_metric_audit_latest.json`.

## V423–V426 local daily R4 range-accumulation closure (2026-07-13)

After external-data work was explicitly abandoned, one new **qualitatively distinct** local daily pure-structure narrative was admitted under a frozen contract:

`confirmed two-sided balance → SSL below range floor + close reclaim → range-high BOS → fresh bearish breaker at/after SSL → first touch/reclaim/hold → next-session open`.

It differs from R1/R2 arbitrary sweep-reversal, C1 generic BOS continuation, and R3 EQL-pool reversal because the prior **two-sided accumulated balance** and break of its exact ceiling are mandatory causal prerequisites.

- V423 generated 4,642 unique semantic candidates from all 4,655 symbols. After one-execution-per-symbol-day de-duplication, takeover supply was 2,038: 2023=206, 2024=374, 2025=965, 2026=492; it passed the pre-outcome support gate (>=40 each year).
- V424 independently rederived every raw-bar prerequisite and lifecycle: 4,642/4,642 passed; chronology failures=0; duplicate event/POI rows=0; duplicate symbol/takeover-day rows=0; forbidden outcome fields=0.
- V425 ran the only permitted frozen T+1 diagnostic (`TAKEOVER_CONFIRMED → next-session open`, fixed 5/10/20D close marks, no TP/SL/window/threshold/exit search). T+1 violations=0.
- R4 failed the fixed usefulness gate: 5D overall n=2,022 / positive=49.06% / avg=+0.4850%; 10D n=2,003 / positive=49.78% / avg=+1.0962% / zone invalidation=31.25%. 2023 5D was 39.50%/-0.3114%; 2024 5D 44.59%; 2026 10D 45.97%/-0.4955% with 39.87% zone invalidation.

**Closure:** `R4_CLOSED_ECONOMIC`. Do not reopen it with range width, sweep depth, holding period, TP/SL, or threshold mining. Any next local daily generator must be qualitatively distinct from R1–R4, first pass the same full-universe semantic/lifecycle/chronology/one-execution audit, and show >=40 takeover seeds in each 2023–2026 year before one frozen replay.

## V427–V430 R5 PO3 closure (2026-07-13)

R5 was a genuinely distinct three-phase generator, not a rerun of R4:

`compact PO3 accumulation → SSL manipulation → bull distribution event → fresh bearish breaker → first touch/reclaim/hold → next-session open`.

V427 supplied 395 unique takeover seeds (2023=45, 2024=45, 2025=228, 2026=77), passing the pre-outcome support gate. V428 independently rederived 985/985 raw-bar candidates; chronology failures, duplicate event/POI identities, duplicate same-stock takeover days, and forbidden outcome fields were all zero.

V429 then performed its sole frozen T+1 replay. It failed economically: 5D n=395 / positive=46.84% / Avg=-0.2477%; 10D n=395 / positive=47.09% / Avg=-0.2188% / zone invalidation=34.18%. The failure is multi-year: 5D 2023=32.56%/-1.1799%, 2024=44.68%/-2.2146%, 2026=32.47%/-0.6134%; 10D worsens in those years.

**Closure:** `R5_CLOSED_ECONOMIC`. Do not re-open PO3 using accumulation width/window, compactness, sweep depth, event delay, retest wait, holding period, TP/SL, targets, or threshold mining. The local daily pure-structure set R1/R2/C1/R3/R4/R5 is now closed. See `/root/.hermes/smc_audit/v430_local_daily_pure_structure_r4_r5_closure_latest.json`.

## V409–V411 causal three-combination closure (2026-07-13)

This branch deliberately changed from scalar filtering to three causal SMC narratives generated directly from all 4,655 daily raw-bar symbols:

- `R1_SSL_CHOCH_DEMAND_OB`: confirmed SSL sweep → bull CHOCH within 20 bars → CHOCH-anchored backward demand OB → first retest/reclaim/hold.
- `R2_SSL_CHOCH_BULL_FVG`: confirmed SSL sweep → bull CHOCH → bullish FVG born 0–3 bars after CHOCH → first retest/reclaim/hold.
- `C1_BOS_DEMAND_OB`: confirmed bull BOS → BOS-anchored backward demand OB → first retest/reclaim/hold.

V409 was outcome-free and causal. V410 used one frozen diagnostic only: `TAKEOVER_CONFIRMED → next-session open`, then fixed 5/10/20-session marks; no TP/SL/threshold search. Aggregate 5D/10D quality was already weak: R1 `-0.2599%/-0.9552%`, R2 `-0.9004%/-1.4774%`, C1 `+0.2152%/+0.4370%`; all had positive rates below 46% and 10D zone invalidation at 35–41% for C1/R1/R2.

V411 then applied a predeclared yearly stability gate (every 2023–2026 year must have n≥40, positive rate≥50%, nonnegative mean mark, zone invalidation≤30%) to frozen V410 rows. **0/6 combo×horizon tests passed.** R1 was negative in 2023–24; R2 was negative in 2023–24 and failed all 10D years; C1 had negative/near-zero years and 10D invalidation 30–43%. T+1 was 100% compliant. Close all three raw daily causal-combination narratives. Because none reached even the frozen economic diagnostic gate, no independent promotion audit is warranted; do not tune their windows, thresholds, entry, or exits.

Artifacts: `v409_causal_signal_combination_latest.json`, `v410_frozen_combo_t1_mark_replay_latest.json`, `v411_combo_yearly_stability_latest.json`.

## V412 Baostock 5/15/30-minute access closure (2026-07-13)

Historical lower-timeframe Baostock is theoretically a new information layer, so a zero-outcome access gate was run before any source build. The provider login now returns `10001011: 黑名单用户，请与管理员联系`; zero price bars were queried after login failure. The predeclared gate required successful login plus non-empty 5/15/30-minute exact-date probes in 2023–26. `availability_gate_pass=false`, `outcome_replay_allowed=false`. This is an access failure, not an economic result. Close the Baostock sub-hourly branch until provider access changes; do not treat an old 60-minute cache as evidence of current 5/15/30-minute availability.

## V413 research-program closure audit (2026-07-13)

Artifact: `/root/.hermes/smc_audit/v413_research_program_closure_latest.json`.

The audit registry checks one concrete artifact per information class (not just a narrative summary). It found **17/17 branches closed, 0 unverified**:

- **10 source-valid but economically closed:** daily causal SMC narratives; canonical daily continuation; complete historical 60min MTF; same-day participation; prior behavior cohorts; exact-time disclosures; 龙虎榜; margin financing; PIT top-shareholder snapshots; strict-prior block trades.
- **7 unavailable under the strict contract:** northbound holdings; mootdx ticks; Eastmoney 5/15/30m; Baostock 5/15/30m; main fund flow; aggregate fund holdings (provider timestamp unproven); ETF share changes (no PIT constituent mapping/timestamp).

The audit first had six false `UNVERIFIED` classifications because historic reports use heterogeneous gate fields; V413 classifier was corrected to treat explicit `*_FAIL__STOP`, `NO_REPLAY`, and strict timestamp/mapping failures as formal source closures. Final verification: `{CLOSED_ECONOMIC: 10, CLOSED_UNAVAILABLE: 7, UNVERIFIED: 0}`.

Program decision: `RESEARCH_FRONTIER_CLOSED__NO_LEGITIMATE_EXISTING_DATA_ITERATION`. Do not reopen any listed branch using alternative thresholds, exits, proxy mappings, or recent-only fragments. The only eligible restart trigger is a genuinely new source with (1) all 2023–2026 V381 identities, (2) date-addressable raw records, (3) verifiable prior-time/publication timestamp, (4) raw price/code alignment, and then exactly one frozen-schema replay.

## V493–V497 weekly bullish-FVG transfer closure (2026-07-15)

After the user explicitly abandoned unavailable external-data directions, one genuinely distinct local higher-timeframe ontology was tested outcome-blind: completed weekly bullish FVG → first post-creation daily touch → later reclaim → later hold → next-open entry. V493 produced 35,781 seeds across 4,897 symbols; V494 independently reproduced all 35,781 with zero mismatch and no outcome fields. V495 then ran one frozen strict-T+1 replay (weekly FVG low -1% SL, nearest already-visible weekly swing-high target, time30, 0.2% fee), and V496 independently recomputed all metrics exactly.

Result: n=34,836; gross WR=56.7028%; net>=0.8 WR=49.3340%; AvgNet=0.3379%; payoff=0.8697; PF=1.0975; SL=37.4699%; T+1=0. The year split invalidates promotion: 2023 n=5,311 / WR=32.4609% / AvgNet=-1.8321% / PF=0.5863; 2024 and 2025 were positive; 2026 was nearly flat (+0.0343%, PF=1.0085). Close this ontology without threshold, conjunction, SL, TP, or hold variants. Artifact: `/root/.hermes/smc_audit/v497_weekly_fvg_demand_transfer_direction_closure_latest.json`.

## V398 exchange ETF share-change feasibility gate (2026-07-12)

Artifact: `/root/.hermes/smc_audit/v398_pit_etf_share_change_availability_latest.json`.

SSE and SZSE both expose complete queryable daily ETF-share snapshots across tested 2023–2026 dates (all 14 SSE/SZSE probes returned non-empty results). This is **not** a usable stock-level signal source under the PIT contract:

- the responses supply ETF-level shares and statistics dates, but no verifiable per-snapshot publication timestamp;
- no historical ETF constituent-weight / as-of mapping is supplied, so an ETF share change cannot be legally attributed to a constituent A-share;
- inferring membership from today\'s holdings, a statutory deadline, or the outcome period would leak future information.

`outcome_replay_allowed=false`; no threshold search or economic replay was run. Close this source. Do not transform ETF share-history availability into a stock signal without a timestamped historical constituent source.

## V415–V419 structure-flip POI and post-reclaim expansion closure (2026-07-15)

Artifacts: `v415_structure_flip_poi_lifecycle_latest.json`, `v416_structure_flip_frozen_t1_replay_latest.json`, `v417_post_reclaim_expansion_lifecycle_latest.json`, `v418_post_reclaim_expansion_frozen_t1_replay_latest.json`, `v419_structure_flip_expansion_closure_latest.json`.

This branch tested a genuinely different pure-structure POI rather than another OB/FVG threshold: the body-top-to-wick-high zone of the confirmed swing-high candle broken by bullish CHOCH/BOS becomes resistance-to-support. V415 generated all-market causal lifecycles across 4,903 symbols. V416 used one frozen execution contract: takeover then next-session open, no entry-day exit, SL 0.5% below zone low, nearest higher already-confirmed swing as TP, 20-session maximum hold, 0.15% fee, pessimistic SL-first same-bar ordering, and serial per-symbol execution.

V416 failed economically despite nominal WR near 60%: R3 SSL→CHOCH structure-flip was n=21,109 / WR=60.01% / AvgPnL=-0.5595% / PF=0.7011 / planned RR median=0.2657; C2 BOS structure-flip was n=58,194 / WR=59.17% / AvgPnL=-0.6091% / PF=0.7345 / RR median=0.2441.

V417 then changed the mechanism, not a scalar threshold: after reclaim/takeover, price had to close above every high from the original event through takeover before the original 30-bar lifecycle boundary. V418 improved signal quality but not economics. R3 reached n=11,053 / WR=67.61% / SL=18.92%, yet AvgPnL=-0.4454% / PF=0.8242 because average win was +3.09% versus average loss -7.82%, and planned RR median collapsed to 0.1327. C2 reached n=25,271 / WR=63.98% / SL=19.52%, but AvgPnL=-0.6529% / PF=0.8059, average win +4.24% versus loss -9.34%, RR median 0.1223. Neither combination had positive average PnL in every 2023–2026 year.

Hard audit passed: T+1 violations=0, negative time-order=0, future target confirmation violations=0, serial overlap remaining=0, and no outcome-parameter search or production/frontend/watchlist write occurred.

**Close this branch.** Post-reclaim expansion genuinely filters passive holds and raises WR, but it enters after price expansion while retaining the original POI invalidation, compressing target room and enlarging residual tail loss. Do not threshold-mine RR, SL width, hold window, or expansion delay on these rows.

## V432 V185 causality/provenance rejection (2026-07-14)

Artifact: `/root/.hermes/smc_audit/v432_v185_causality_provenance_latest.json`.

A production-rebuild audit found that V185 was never a causally approved production source despite later rematerialization setting production flags:

- The formal V185 source decision was `V185_COMBINED_PRODUCTION_GATE_PASS__SHADOW_ONLY` with `production_write=false`, `frontend_write=false`, and `watchlist_write=false`.
- All 247 V175 component rows entered 2 bars before takeover-2 legal entry and 3 bars before takeover-3 legal entry.
- All 87 child rows selected `v132_bull_count_3==3`, which is defined from the three bars after reclaim, but every child row lacks `reclaim_idx`, `v132_entry_after_confirm_idx_3`, `touch_idx`, and `zone_idx`; current raw-scanner provenance cannot be reconstructed or audited.

Decision: `REJECT_V185_AS_PRODUCTION_BASELINE__HISTORICAL_ADVANTAGE_NOT_CAUSALLY_PROVEN`. Preserve its 334 rows only as rejected research history. `v185_daily_rematerialize.py` now fail-closes to an empty book and cannot restore production flags unless a causality audit explicitly allows reconstruction.

Operational lesson: a rematerializer must never upgrade a source whose formal artifact is shadow-only. Before running any current scanner, validate source promotion state, chronology, and selector provenance. If refresh or causality gates fail, stop scanner, shadow, ingest, API reload, and buying; do not substitute the wall-clock date for the latest completed market date or use an intraday partial daily candle.

## V431 local daily pure-structure final registry closure (2026-07-13)

Artifact: `/root/.hermes/smc_audit/v431_local_daily_structure_frontier_closure_latest.json`.

V431 re-read all required closure artifacts without opening raw prices, candidate rows, outcomes, watchlists, or production surfaces. It verified `audit_failures=[]`, all source artifacts present, zero production/frontend/watchlist writes, R5 independent semantic integrity passed, and **zero unclosed defined local-daily ontologies**.

The closed set is exhaustive for currently defined local OHLCV pure-structure generators:

- R1: SSL → CHOCH → fresh demand OB → reclaim/hold
- R2: SSL → CHOCH → post-creation bull FVG → reclaim/hold
- C1: Bull BOS → fresh demand OB → reclaim/hold
- R3: EQL pool → SSL → CHOCH → fresh demand OB → reclaim/hold
- R4: two-sided balance → SSL reclaim → range-high BOS → breaker → reclaim/hold
- R5: PO3 accumulation → SSL manipulation → bull distribution → breaker → reclaim/hold

**Decision:** `LOCAL_DAILY_PURE_STRUCTURE_RESEARCH_COMPLETE__NO_DEFINED_LEGAL_NEXT_REPLAY`.

Do not reopen these six ontologies with parameter, threshold, window, entry, TP, SL, target, or exit mining. The only strategy-research restart condition is a new causal ontology demonstrably distinct from R1–R5; before one frozen T+1 replay it must pass a full-universe no-outcome semantic/lifecycle/chronology audit, one execution per stock/day, and at least 40 takeover seeds in each of 2023–2026. Until then only operational monitoring (data freshness, semantic drift, scanner provenance, frontend/API consistency) remains; it is not strategy research.

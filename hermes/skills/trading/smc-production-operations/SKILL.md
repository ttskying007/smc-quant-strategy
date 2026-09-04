---
name: smc-production-operations
description: Operate and verify SMC production, research-replay, scanner, watchlist, and monitoring paths without mixing historical artifacts with current production state.
---

# SMC Production Operations

## Use when

Use for SMC dashboards, production promotion/rollback, manual scans or replays, `EMPTY_BOOK`, watchlist writes, position monitoring, and API/UI consistency verification.

## Operating model

Keep these three domains separate at every API and UI boundary:

| Domain | May write positions/watchlist? | Purpose |
|---|---:|---|
| Production | Yes, only after an independently verified promotion gate | Current executable candidates and lifecycle state |
| Research replay | No | Reproducible causal evaluation and diagnostic evidence |
| Historical artifacts | No | Audit only; never a fallback source for current candidates |

`EMPTY_BOOK` is a fail-closed production state, not a ban on research or current scanning. It must prevent production writes and candidate backfills while allowing explicit no-write research replays **and current-epoch scanner execution**. Never equate EMPTY_BOOK with “scanner not run” or “research complete”: expose the current scanner’s epoch, timestamp, funnel, partial/full candidates, and exact admission blocker separately from production state.

When the registry has no promoted strategy, the operational contract is:
- run the current outcome-blind scanner against the newest committed epoch in no-write mode;
- expose current candidates as `RESEARCH_BLOCKED_NOT_EXECUTABLE` / `PENDING_NEXT_OPEN` rather than hiding them;
- keep `buy_enabled=false` until the new ontology independently passes support, Oracle, frozen strict-T+1 replay, and production gates;
- verify UI/API current scanner fields directly, not only registry state;
- treat “EMPTY_BOOK + scanner ran + candidates exist” as a valid intermediate state distinct from “EMPTY_BOOK + scanner skipped.”

## Required workflow

1. **Discover the authoritative production registry** before changing routing. Treat its strategy, state, buy flag, and invariant flags as the source of truth.
2. **Classify the requested operation** as production execution, no-write replay, or historical audit. Do not reuse one endpoint outcome to mean all three.
3. **For manual replay in EMPTY_BOOK**, run only the latest causal frozen replay contract. Return execution success separately from promotion eligibility.
4. **For production writes**, require all of: an approved strategy, a current full-market scanner output, row-level authorization, strict T+1 compliance, and gate pass. Historical trade files cannot satisfy any of these conditions.
5. **Never make a blocked production action work by falling back** to an old engine, old active-picks file, or a historical completed-trade artifact.
6. **Make UI semantics match the operation**: label no-write actions as research/frozen replay, show `EMPTY_BOOK` explicitly when applicable, and do not call a successful replay a production promotion. A frozen replay’s last response/pick date must be labeled as the historical study cutoff—not as the current latest selection date—and the page must separately show the committed current data date plus `current latest selection: none` when production scanning is intentionally skipped.
7. **Verify both layers**: invoke the API directly, then use the browser to click the exact UI control and read its displayed result.

## Research-frontier closure and autonomous continuation

For a new SMC research direction, execute the next preregistered gate autonomously without repeatedly asking for confirmation. Treat the pipeline as terminal when the available-data frontier is exhausted:

1. qualify the source and PIT publication timing;
2. generate outcome-blind causal seeds;
3. require independent identity-oracle equality;
4. apply the pre-outcome support floor;
5. run exactly one frozen strict-T+1 replay only if all prior gates pass;
6. independently audit replay metrics and production eligibility.

A failed source, identity, or support gate closes that ontology before outcomes. Do not rescue it by changing windows, thresholds, years, symbols, subsets, POI, SL/TP, holding period, or by borrowing prior outcomes. Close with exact counts, gate comparisons, artifact paths, production registry state, and permitted/restricted next research dimensions. A genuinely independent PIT or full-history microstructure source is a new ontology; merely changing the timeframe or price-derived logic is not.

### Durable pending / admission-freezing rule

A `PENDING_NEXT_OPEN` row created from the newest committed epoch is neither a historical artifact nor an immediately executable buy. Persist, with the row, its decision-time license snapshot (strategy, release artifact/hash, scanner epoch, structural SL/TP, execution contract, and immutable-row digest).

- A later aggregate replay or research-gate failure may block **new admissions**, but must not retrospectively relabel a signed current-epoch pending row as historical, stale, or research-invalid.
- The signed row may be evaluated only on its first eligible-session opening quote. Retry a stale quote only within that same opening session; never fill it on a later session.
- If the exact opening-session quote cannot be proven, record the source failure and close it as an unfilled/indeterminate audit outcome—never manufacture a historical fill.
- Controller runs must use a nonblocking durable lock so retries cannot create duplicate entries.
- UI/API must read durable pending rows for current-pending state, not a subsequently overwritten `*_latest` release/scanner artifact.
- Scanner materialization is not production admission: even when research/promotion gates fail, continue the current-epoch **outcome-blind, no-write** scan and expose any rows as `RESEARCH_BLOCKED_NOT_EXECUTABLE`; do not erase the evidence by returning zero files/zero rows.
- Preserve the distinction in the UI: `authorized pending`, `blocked current scanner candidate`, and `no current candidate` are three separate states.
- For exact-next-open scheduling, retry every minute of the opening window. Validate exchange-open status with an index quote separately from the individual symbol quote; a later weekday is eligible only if every intervening weekday was recorded as a confirmed exchange closure. A stale symbol quote on a proven open market expires after that opening session and must never become a late fill.

### Stale-date / “no picks” diagnostic

A date far behind the current market date is not, by itself, proof that the scanner failed. Diagnose in this order:

1. Read the registry and committed epoch, then query `/api/summary` and `/api/live-prices`. Record `production_strategy`, `buy_enabled`, `active_buy_valid_count`, `dataDate`, `scanner_state`, and current `picks`.
2. In a legitimate fail-closed state, expect a fresh committed market date with `NOT_RUN_EMPTY_BOOK` and `picks=[]`; do not treat the absence of a scan date as stale data.
3. Inspect production, live, logs, frozen-research, and legacy-artifact pages separately. A legacy artifact's last signal date is an audit cutoff, never the current last-pick date.
4. Confirm the refresh manifest/epoch and scheduled observer output. A fresh committed epoch plus a blocked scanner proves data ingestion is alive and production selection is intentionally skipped.
5. If wording can conflate the two domains, make a wording-only repair: label legacy dates `最后历史信号日`, state `当前最新选股日：无` for blocked production, and avoid naming mixed research/history views “当前选股”. When a frozen-replay table shares a page with production state, put its cutoff and `非生产选股` directly in that card’s heading—not only in explanatory body text—because the prominent terminal date is naturally read as a last-pick date. Never revive a legacy selector or historic trades to make the UI appear current.
6. After the repair, syntax-check and restart the actual server. Verify direct API assertions (`buy_enabled=false`, `picks=[]`, current epoch date), raw HTML assertions for the revised labels, and the browser-rendered labels.
7. **Prevent stale-but-open dashboard pages.** The `EMPTY_BOOK` server-rendered branch must include a bounded refresh mechanism (for example, a 120-second meta refresh) just as the normal dashboard does. Render the committed epoch ID/market date plus scanner `generated_at` and `response market date` directly on the page. If the causal table displays a prior event date such as `sweep_date`, label it as the preceding chain event—not the scanner response date—so users cannot mistake a correct multi-day sequence for an unsynchronized frontend.
8. **Enforce exactly one scheduler owner.** Enumerate system cron and any in-process scheduler. When system cron owns post-close refresh, the frontend service/watchdog must explicitly start with the in-process scheduler disabled. Parse scheduler environment flags as explicit truthy values (`1`, `true`, `yes`, `on`) rather than treating any non-empty string as enabled; `SMC_INTERNAL_SCHEDULER=0` must genuinely disable it. Verify the actual restarted process logs the disabled state and that the scheduler-status surface agrees.
9. Verify `/api/logs` independently. In `EMPTY_BOOK`, it must return the current registry and committed epoch, not an archival `ops_latest` payload whose dates or legacy-engine fields can be mistaken for current scanner state. Route the endpoint through the same current-state snapshot used by the fail-closed logs page.

See `references/stale-date-empty-book-ui-diagnosis.md` for the reproduction and acceptance checklist. For a compact API/epoch/browser proof plus a fail-closed cron-wrapper no-mutation probe, see `references/fail-closed-stale-pick-date-and-cron-probe.md`. For a current committed epoch versus a visually prominent frozen-research cutoff, including the archival-`ops_latest` pitfall and browser/API assertions, see `references/empty-book-fresh-epoch-versus-historical-cutoff.md`.

### Selection-supply and scheduler-truth escalation

An `EMPTY_BOOK` state is valid only when its cause is continuously observable. A prolonged EMPTY_BOOK is an operational incident against the user's selection/execution objective, not a sufficient research-closure result. Do not report the system as "complete" merely because fail-closed behavior is correct; explicitly diagnose and, where authorized, repair the production path.

When a user reports weeks or months without picks or live trades, separate and report four independently evidenced layers before concluding: (1) refresh/epoch health, (2) raw current scanner supply and causal funnel, (3) release/license/admission state, and (4) scheduler and live-execution activity. A healthy committed epoch does not imply a current setup; a zero current setup does not imply the scheduler failed; a revoked license does not justify calling the scanner "not run" if a no-write scanner artifact exists.

The dashboard/API must distinguish at least these states:
- `NO_CURRENT_SETUP`: current-date scanner ran and full causal setup count is zero;
- `CURRENT_SETUP_BLOCKED`: current-date rows exist but release/admission is blocked;
- `NO_LICENSED_STRATEGY`: production execution is disabled by the authoritative registry;
- `LIVE_READY_NO_CURRENT_SIGNAL`: a licensed strategy ran with no executable current row.
Do not collapse all of them into `NOT_RUN_EMPTY_BOOK`, and do not use historical trades to make any state look active.

For a prolonged outage, preserve an incident reconciliation artifact containing the date window, committed epoch/date, scanner funnel (fresh → structure → sweep → response → full setup), release failed checks, registry authorization fields, scheduler return codes, pending count, position count, and live-monitor checks. This artifact is diagnostic/observability output only and must not mutate production.

An EMPTY_BOOK can be the correct safety result while still being an incomplete product outcome. If the user asks to restore selection or real-time trading, treat that as a production operations repair request: first identify whether the blocker is license, current signal supply, refresh, scheduler, or execution; never substitute a research-frontier closure report for that diagnosis. When the user reports a prolonged absence of selections, do not answer from the registry alone and do not focus only on cache completion. Reconstruct the market-date sequence as four independent facts: **refresh/epoch health**, **current raw scanner supply**, **release/admission status**, and **actual scheduler execution**.

See `references/prolonged-empty-book-incident-reconciliation.md` for the evidence matrix and state-normalization checklist.


1. Read the scanner-time artifact *before* release filtering. Distinguish `NO_CURRENT_SETUP` (licensed strategy, zero current rows) from `CURRENT_SETUP_BLOCKED` (rows exist but a release gate blocks admission) and `NO_LICENSED_STRATEGY` (no strategy can make a pending row).
2. Enumerate every scheduler owner—user crontab, `/etc/cron.d`, Hermes cron, in-process scheduler environment flag, and live process command line. A stale scheduler-state JSON or a job label is not proof of either execution or nonexecution.
3. Parse actual observer logs by committed market date and record epoch ID, candidate/pending count, release state, controller return code, and refresh failures. A successful cron exit without a current-date artifact is insufficient.
4. If the displayed scheduler state names retired strategy jobs, atomically replace that *display/observability state* with the real scheduler ownership and preserve the old lineage only as audit history. Do not re-enable old jobs merely to make activity appear continuous.
5. Treat unexplained consecutive empty sessions as an operational escalation. The escalation must make the reason visible and decide whether new-source qualification is needed; it must never lower frozen gates, revive historical picks, or turn shadow rows into buys.
6. A daily scanner report must expose an **outcome-blind current-date funnel**, not only final pending rows: fresh files → each causal stage → complete current setups. Persist every partial row that reaches the first meaningful structural stage with `furthest_stage` and its exact `next_required` condition. Render all rows/counters in the UI as `RESEARCH_BLOCKED_NOT_EXECUTABLE`; neither a blocked row nor a partial row may become a pending order, watchlist row, position, or buy. This distinguishes `no raw setup`, `partial chain stopped`, and `full setup blocked by release`.
7. Treat a rejected refresh epoch as a first-class data-plane incident, not an `EMPTY_BOOK` result. Persist actual scheduler outcomes—including every component return code and controller stderr—and update the UI state after every run. When a provider returns only a mutable intraday bar, preserve the preceding committed daily cache only with a separately verified market-open witness; never silently mix an adjusted fallback series or assume a provider's market-status field exists. See `references/intraday-provider-refresh-and-scheduler-truth.md`.
8. Audit scanner anchor semantics before interpreting a funnel. A fixed `swing_idx = sweep_idx - right - 1` only tests one immediate offset, not any prior confirmed liquidity swing. For each current sweep, choose the nearest prior right-confirmed, unmitigated swing actually pierced and reclaimed; emit swing, confirmation, sweep dates, distance, and multiplicity. This semantic repair invalidates prior results and requires a full seed → independent Oracle → one frozen T+1 replay chain.
9. Paginate large observation surfaces server-side. Never render a full multi-thousand-row list or merely hide it with client-side JavaScript. Preserve totals, show a bounded batch with page/range controls, and make the symbol summary and detail table use the identical slice. See `references/current-scanner-anchor-and-large-list-paging.md`.
10. When asked whether a scan is “full market” or “filtered too much”, prove it per file: enumerate stale files (suspended/delisted) and fresh-without-structure files (new listings, consumed anchors), then show the causal funnel stages reconcile arithmetically. Distinguish universe/data-availability filtering from causal signal filtering; never answer a completeness challenge with an aggregate table. Recover stopped-at-stage counts from the persisted `furthest_stage` labels, reconcile each funnel arrow in code (`stage = stopped + next`), and verify the rows nearest the final stage individually with their sweep-high/response-close values. See `references/scanner-universe-completeness-vs-causal-funnel.md`.

For a concrete evidence matrix, scheduler-reconciliation pattern, and the distinction between source-cache cleanup and strategy repair, see `references/selection-supply-and-scheduler-truth.md`. For the four-layer no-pick diagnosis, source-only reopening discipline, and the HKEX Northbound retention/quarterly-granularity qualification pitfall, see `references/source-qualification-and-no-pick-closure.md`.

### Reboot and daily-close cadence diagnostic

When a user reports that the frontend did not auto-sync after a reboot, first distinguish service recovery from the normal timing of a close-based daily epoch. Compare current boot time with the unit's first start time in the current boot; `enabled` now does not prove that the unit was installed and started at boot. Verify the dashboard service owner, `network-online` dependency, restart policy, actual current-boot post-close scheduler invocation, committed epoch manifest, and browser-rendered epoch together. Do not rerun a completed post-close observer merely as a test: it can race and rewrite current artifacts. A morning absence of a finalized same-day daily bar is expected when the configured job is post-close; explain the cadence separately from genuine service failure. If recovery is required, use one bounded supervised restart and assert a new PID/listener, rendered committed epoch, and unchanged fail-closed production state. See `references/reboot-safe-frontend-and-daily-epoch-verification.md`.

## Research-frontier stop rule

A standing request to research continuously does **not** authorize unlimited variants of a closed ontology. Before a replay, reconcile the completed-hypothesis inventory with the pre-registered gates.

1. A candidate is genuinely new only when it adds an independent causal information dimension—not when it changes a daily-OHLCV event window, volume threshold, structure label, stop/target, holding period, year slice, or regime bucket of a closed object.
2. When the registered inventory is closed, do one concrete no-write prerequisite check: re-probe the required source and run its scope/coverage authorization gate.
3. `N/N` source-local files prove cache integrity only; they do not prove full-history availability, canonical-universe coverage, same-source continuity, or production eligibility.
4. Never join a recent partial intraday source to an older provider cache to fabricate a 2023–2026 replay series. Keep differing price/volume series isolated.
5. If the PIT or complete same-source OHLCV prerequisite remains unavailable, explicitly close the current research frontier and retain `FAIL_CLOSED` / `EMPTY_BOOK`. Report the measurable data-contract condition that reopens research instead of running a weak near-term study.

See `references/research-frontier-and-source-readiness.md` for the evidence and decision pattern. For the full-universe audit versus single-symbol/shard artifact pitfall and the correct source-read-gate handoff, see `references/source-scope-gate-and-full-audit.md`. For the V539–V547 15m price-only and volume/displacement closure, independent-oracle mismatch discipline, and the precise data condition for legal reopening, see `references/intraday-volume-frontier-closure.md`. For the HTF→LTF / m60 branch reconciliation rule—where a timeframe swap is a prohibited variant rather than a new ontology—see `references/htf-ltf-frontier-reconciliation.md`. For launching several genuinely new data-information lanes without reopening closed OHLCV variants, and for a resumable, source-isolated historical build, see `references/multilane-pit-source-qualification.md`. When a PIT announcement-source pilot passes but its first canonical-universe pass is degraded by request failures or page caps, use `references/pit-event-source-retry-and-pagination-gate.md`: recover the source-only transport/pagination contract before declaring the source unavailable or reading any outcomes. When a previously incomplete source cache later becomes complete, use `references/source-readiness-vs-frozen-ontology.md` to distinguish a repaired source contract from a closed economic ontology; cache completion cannot authorize variants of a failed frozen replay. For title-metadata versus document-payload PIT sources, deterministic payload identity/timestamp pilots, explicit source-failure accounting, and the `PIT_PENDING_PUBLICATION` tail rule, use `references/pit-payload-source-qualification.md`. For full metadata-denominator payload builds, same-announcement official-PDF fallback, dual-parser semantic identity parity, and strict closure of failed exact text objects, use `references/pit-payload-semantic-frontier.md`.

## Partial-history research correction

Incomplete historical coverage is not a standalone reason to stop strategy research. When a source-isolated, PIT-valid local scope has complete usable years, continue research-only ontology discovery inside that declared scope; do not represent it as full-history production eligibility. Use outcome-blind support → independent identity Oracle → one frozen strict-T+1 replay, and close only the tested ontology when it fails.

For external-state transitions, define state reset explicitly: a non-qualifying day (including zero/unavailable intensity) ends a high-state run. The independent Oracle must compare canonical identities after the same `symbol + planned_entry_date` earliest-event rule; any missing/extra identity blocks replay until the contract mismatch is repaired and outcome-blind seeds are regenerated.

For PIT announcement-source recovery, use `references/pit-event-source-retry-and-pagination-gate.md`. For partial-history PIT strategy discovery, external transition-state reset, identity-Oracle reconciliation, and frozen replay closure, use `references/pit-external-event-identity-oracle.md`. For a genuinely new PIT corporate-event dimension, build and audit a metadata-only, fully paginated catalog before defining any causal chain; see `references/pit-new-event-dimension-catalog.md`. For semantic primary-disclosure filtering, exact identity-Oracle parity, and the crucial distinction between seed support and final executable-trade support, see `references/pit-event-catalog-semantic-filter-and-execution-support.md`. Before opening outcomes on any event-driven ontology, apply `references/outcome-blind-event-seed-support-and-closure.md`: count independent causal chains rather than repeated event disclosures, enforce fixed annual support, and close support failures before Oracle or replay. For the Eastmoney institutional-survey schema pitfalls and the measured datacenter transport contract (page_size=50, workers≤4, per-thread keep-alive sessions, background resumable builds), see `references/institutional-survey-source-qualification.md`.

### Mandatory final reconciliation after autonomous frontier work

When the user asks for continuous research until a qualitative change, do not stop at the latest branch result. Reconcile the full authorized inventory before declaring completion: current price-only frontier, every genuinely independent PIT branch attempted after the prior closure, source/cache qualification, and the production registry. The completion artifact must assert that support failures opened no outcomes, closed ontologies were not rescued by variants, and no production/watchlist/position/registry writes occurred. Report the exact terminal decision and the only condition that can legally reopen research.

A source-health pass is not a strategy pass. Keep provider namespaces isolated and witnesses observational. For retained no-write monitors, invoke the exact dependency-complete interpreter, verify the wrapper is executable, run once under fail-closed state, and compare the production-registry digest before and after. Schedule only source-health/coverage checks; the monitor must not invoke scanners, replays, watchlist writers, position controllers, or promotion code. Record source health separately from strategy authorization.

See `references/frontier-completion-and-source-monitor-handoff.md` for the reconciliation schema and monitor handoff checklist.

## Canonical causal seed reconstruction

When a strategy claim comes from a broad historical candidate stream, rebuild its signal from raw bars before trusting legacy candidate counts or performance. This is research work, not a production promotion.

1. Generate an **outcome-blind** seed set from one declared same-source OHLCV universe; do not read trade/PnL/exit/target/stop artifacts.
2. For bullish BOS, require a right-confirmed swing high that was known before the event, with prior close at or below the level and current bullish close strictly above it. A close that merely remains above an old high is not a new BOS.
3. Consume every pivot crossed by one displacement bar. A later dip-and-recross of a consumed level cannot mint a second structural event.
4. Locate a demand OB backward from the BOS in the declared lookback, preserving the exact origin candle and zone values. Do not generate OBs by scanning arbitrary candles forward.
5. Materialize the full lifecycle as strict ordered records: BOS → zone touch without close invalidation → later reclaim → later hold → following-session eligibility.
6. Run a raw-bar semantic audit across **every** seed, validating pivot confirmation, first crossing, OB provenance/price identity, lifecycle order, next-session entry, and absence of outcome fields. Only then freeze one T+1 replay contract.

This catches two common false-positive sources: repeated BOS emission after price remains above an old pivot, and forward-scanned OB labels that are not anchored to the actual structural break. See `references/canonical-causal-seed-audit.md`.

## Frozen economic closure and no-rescue rule

Semantic correctness and high sample support do **not** constitute a production strategy. After an outcome-blind causal seed and all-seed independent semantic audit pass, permit exactly one preregistered strict-T+1 execution replay and independently recalculate metrics from its emitted trade CSV.

1. Pre-register the complete execution contract before outcomes are opened: entry date/price, structural stop, pre-entry unconsumed structural target with minimum planned RR, first-exit collision rule, fee, hold limit, and per-symbol serial-position policy.
2. Separate invariant verdicts from economic verdicts. Zero chronology violations and all planned RR values meeting the minimum prove correct execution, but cannot compensate for a miss on win rate, PF, average return, or any annual requirement.
3. Compute every fixed gate both overall and by decision year. A pass in a later bull-market year cannot offset negative or non-compliant earlier years.
4. On a frozen gate failure, close the exact ontology. Do not rescue it through selectors, thresholds, date windows, stock subsets, timing changes, stop/target changes, holding changes, or market-regime labels. Retain EMPTY_BOOK and only consider a genuinely independent PIT information dimension or a new complete canonical intraday source.
5. Write a compact frontier-closure artifact that preserves seed support, semantic-audit count, one frozen replay result, independent metric recalculation, failed gates, and the precise criterion that can reopen research.

The canonical daily BOS→backward-demand-OB→reclaim validation provides a concrete full-universe reference: semantic pass can coexist with economic failure, and that outcome must be treated as a valid strategy rejection rather than a reason to optimize. See `references/frozen-smc-economic-closure.md`. For the SSL-sweep → CHOCH/displacement → causal POI lifecycle, first-touch cancellation, complete frozen-contract correction, and economic closure protocol, see `references/causal-state-machine-frozen-replay-closure.md`. When an otherwise causal W→D→60m chain can survive after its upper timeframe permission or POI has failed, treat continuous validity as a separately preregistered ontology—not as a retrospective filter; see `references/persistent-validity-smc-state-machine.md`.

## Contract for no-write replays

The response must include at least:

- execution `ok` status;
- replay engine/version and deterministic contract identifier;
- trade count and key metrics;
- strict T+1 invariant count;
- `production_gate_pass` as a separate Boolean;
- `production_write=false` and `watchlist_write=false`;
- a decision/state that explains why production remains disabled when the gate fails.

A promotion-gate failure after a correct replay is a **research result**, not an endpoint execution error.

## Market-data provenance and universe-coverage gate for research

Before any multi-timeframe replay, signal study, or promotion decision, verify the historical OHLCV contract:

0. **Establish the denominator before reporting progress.** Audit the cache against a dated, canonical master universe—not against files already cached. Keep SH/SZ equities, BJ equities, ETFs, broad indices, and industry/sector/board series as separate asset classes. `N/N cache-integrity pass` proves only cached-subset integrity, never full-market coverage by itself.
   - A subset may support explicitly labelled `CACHED_SUBSET` diagnostics after same-source integrity passes.
   - It must fail closed for full-market conclusions, strategy promotion, and production if any required asset class is missing or coverage is below 100%.
   - Report canonical count, cached-complete count, missing count, coverage percentage, excluded asset classes, and missing reasons.
   - Do not use an alternate provider to fill missing symbols/bars or change the denominator.

1. Store each provider under its own `source_raw/<provider>/` namespace; never fill a missing bar from another provider.
2. Require each bar to record `source`, `adjustment`, `requested_range`, `received_range`, `provider_timestamp`, `coverage_audit`, and `cross_source_validation`.
3. Audit within one source before use: valid and ordered daily bars; 16 A-share 15m slots/day; 4 60m slots/day; weekly derived from same-source daily; 60m derived from same-source 15m.
4. Treat cross-provider overlap as evidence only. Differences in prices, volume, adjustments, or timestamps prohibit substitution and preserve isolation.
5. Separate source-local research authorization from cross-source-validated promotion. Label same-source research honestly; do not claim independent validation without a full-range external audit.
6. A provider outage must fail closed for new builds; it must not create false permanent-symbol quarantine or silently revive old artifacts as current data.
   - Tencent `fqkline` can return only a single same-day row for some BJ symbols. Treat it as mutable while Tencent reports `*_open_交易中`. If a partial response is eligible for a completed session, it may replace **only the existing cache tail date**; all earlier overlaps must align, and a one-row response must never overwrite history. Some endpoint variants omit a market-status field, so distinguish provider-confirmed closure from the normal time-based session cutoff in the audit.
7. For cache construction that can outlast an interactive process, use a durable, restartable controller. It must calculate missing symbols from the intersection of all required committed frames, persist atomic progress, serialize writers with a lock, apply bounded retry backoff, and verify recovery by terminating one controller instance and confirming a new PID resumes safely. A successful partial-range build remains research-only.

See `references/multisource-ohlcv-provenance.md` for the cache contract and verification pattern, `references/universe-coverage-gate.md` for the canonical-denominator and full-market release gate, and `references/resumable-source-cache-controller.md` for durable cache completion.

## Release gates and invariants

- No same-day A-share exits; audit this as a hard invariant.
- A current candidate must originate from the same current scanner and causal contract used by the tested strategy.
- Historical artifacts must remain tagged and isolated from active candidate, monitor, and live-price views.
- A production registry with no strategy or `buy_enabled=false` must leave the book empty.
- Avoid silent exceptions around routing, promotion, or write gates; report the state and invariant which blocked the operation.

## Active-production registry routing

When a newly licensed production strategy coexists with legacy `EMPTY_BOOK` or rejected-engine artifacts, the production registry is authoritative at **every** UI and API boundary. Do not let a legacy artifact-specific branch run before the current registry branch.

1. Route the active registry strategy before legacy report checks in summary/status endpoints.
2. Build logs from the current controller state, current committed scanner report, pending-order snapshot, and real positions—not a generic historical `ops_latest` file.
3. Return zero current candidates/positions as `LIVE_READY_NO_CURRENT_SIGNAL` when applicable; never relabel this as `EMPTY_BOOK`.
4. Expose only active-strategy positions and durable current pending rows. Historical trades remain audit-only.
5. Keep post-close scanning distinct from next-open execution and intraday monitoring. A restored execution cron must not duplicate the scanner job. Enumerate every scheduler owner (`crontab -l`, `/etc/cron.d/*`, and any in-process scheduler flag): each post-close observer must have exactly one enabled owner. Duplicate invocations waste full-market refreshes and can race to rewrite the epoch/registry even when production is fail-closed.

**Pitfall:** a dashboard page can correctly follow the registry while `/api/summary` still takes a later legacy V185/V88 fail-closed branch. Directly test dashboard, logs, monitor, live, `/api/summary`, `/api/picks`, and `/api/live-prices` after each registry transition.

**Fail-closed state-normalization pitfall:** do not route `EMPTY_BOOK` UI/API behavior by checking one literal registry state such as `state == 'EMPTY_BOOK'`. A revoked strategy can use a more specific state (for example `FAIL_CLOSED_REPLAY_GATE_FAILED`) while `production_strategy` is `null` and `buy_enabled=false`. Derive the no-production branch from the authoritative authorization fields (`production_strategy is None`, plus buy permission where execution is relevant), so a failed gate never falls through to a legacy backtest or historical artifact. After a routing change, restart the actual server and verify the browser-rendered page—not only the handler/API response. See `references/fail-closed-registry-routing.md`.

**Numeric artifact pitfall:** historical trade JSON may serialize `pnl_pct` and related fields as strings. Coerce at the API calculation boundary rather than comparing raw values or rewriting audit artifacts; then restart the real server and verify the exact endpoint returns JSON. Do not put an import such as `from pathlib import Path` inside an endpoint that already uses global `Path`, because Python treats it as a function-local binding. See `references/dashboard-numeric-contract-and-restart-verification.md`.

**Fresh-cache / fail-closed pitfall:** do not make an `EMPTY_BOOK` dashboard report an old registry-embedded data epoch when a newer cache epoch is committed. Report cache freshness from the committed manifest while keeping strategy authorization exclusively registry-driven. Do not branch only on the literal `state == 'EMPTY_BOOK'`: a specific revoked state such as `FAIL_CLOSED_REPLAY_GATE_FAILED` must take the same no-production route when `production_strategy is None`. Otherwise stale legacy scanner/ops metadata can masquerade as a current last-pick date. See `references/transactional-daily-cache-and-empty-book-freshness.md` and `references/fail-closed-freshness-and-legacy-status.md`.

## Pending-next-open lifecycle, gate revocation, and reporting

A current-epoch structural scanner row is not a current pick simply because it appears in a report. Make the exact lifecycle visible: `PENDING_NEXT_OPEN` → fresh following-session opening quote → structural-range acceptance → `BUY_VALID` → durable watchlist/position write. `PENDING_NEXT_OPEN` is non-executable and must never be described as tradable, selected, or bought.

A later aggregate/research gate failure freezes **new admissions**; it does not retroactively revoke a row already authorized at its own current committed epoch. Persist decision-time authorization on every pending row: strategy, license decision/timestamp, immutable release-artifact path, scanner epoch ID, structural stop/target, response date, and exact-next-session contract. A valid frozen authorization must match the row’s `data_epoch_id`.

Use `ADMISSION_FROZEN_PENDING_EXECUTION` when new rows are blocked but previously authorized pending rows remain. On the exact eligible next session, accept only a fresh quote dated that session and only when `stop < open < target`; otherwise record the rejection. If no fresh quote exists on that exact session, retain the row only through that session and then close it as `EXPIRED_MISSED_EXACT_NEXT_SESSION_OPEN`. Never fill it at a later open. A legacy row revoked before any exact-open observation is `LEGACY_INDETERMINATE_WRONGLY_REVOKED_BEFORE_EXACT_OPEN`, not a price rejection and not historical backfill.

`*_latest.json` artifacts are mutable pointers, not immutable evidence of a past promotion. UI/API must source live pending rows from the durable pending ledger, label that source, and keep them separate from scanner latest, frozen replay, and legacy artifacts. Schedule the chain as committed refresh → current scanner → same-run release snapshot → shadow validation → durable pending write; shadow must not read a previous-cycle `latest` artifact.

When explaining a disappeared setup, provide its symbol, response date, decision-time authorization, expected execution date, every quote-freshness attempt, terminal reason, closure time, and whether any watchlist or buy write occurred. Explicitly correct any earlier wording that conflated `PENDING_NEXT_OPEN` with `BUY_VALID`.

See `references/pending-next-open-gate-revocation.md` and `references/current-epoch-pending-lifecycle.md`.

## Structural target validity and gate revocation

A structural upside target must remain **unconsumed** at the entry decision: require `target > max(entry_open, response_bar_high)`. A nearest prior confirmed high already crossed by the completed response bar is consumed liquidity, not a future target. This rule is causal—not future leakage—and must be applied identically in frozen replay, independent audit, scanner-time materialization, live order payloads, and any structural-RR gate.

When repairing this semantic rule changes the promotion result, expire every unfilled `PENDING_NEXT_OPEN` row, clear the active strategy, retain the committed epoch plus explicit blocker reason, and make market-open a safe no-op. Scanner and release artifacts must remain valid, explicit blocked outputs with zero current rows; API/UI must not fall through to a legacy historical engine. Use a fixture with one consumed and one unconsumed prior high, then assert the scanner selects the unconsumed high; assert no candidate remains when all targets are consumed. See `references/structural-target-and-gate-revocation.md`.

## Scheduler reconciliation after gate revocation

A gate revocation is incomplete until the scheduler is reconciled. Enumerate every cron job in the rejected strategy lineage, inspect wrapper subprocess calls rather than trusting labels such as `shadow` or `observer`, and pause any job that can materialize candidates, create pending orders, execute next-open orders, or monitor/advance positions. Preserve only explicit source-health or cache-integrity monitors that cannot mutate production state. Re-list jobs after pausing and store the job IDs and closure reason in a no-write audit. **Also verify every retained cron wrapper is executable (`stat` mode includes execute bit); a 0600 shell wrapper produces a silent `Permission denied` operational failure even when the cron line and Python target are correct. A no-write Python monitor also needs a self-contained interpreter: test the exact wrapper/shebang (not merely `python3 script.py`) and assert imports plus its latest report succeed; a managed Hermes/system interpreter may not include source dependencies such as `baostock`, `pandas`, `openpyxl`, or `mootdx`. Use an isolated fixed virtualenv in the wrapper or shebang rather than modifying the OS-managed Python. After restoring execution, invoke it once while fail-closed and assert its output is a no-op with the registry unchanged.** See `references/fail-closed-cron-reconciliation.md`.

## Verification checklist

1. Syntax-check and restart the server.
2. Call the manual replay endpoint in `EMPTY_BOOK`.
3. Confirm replay succeeds without production mutation.
4. Confirm strict T+1 violations are zero.
5. Confirm no current picks, positions, or watchlist rows were created by the replay.
6. Click the UI control in a browser and verify the same result text and semantics.
7. Confirm the live/monitor pages do not display historical rows as current candidates.

See `references/empty-book-readonly-replay.md` for a concrete failure mode and acceptance pattern.

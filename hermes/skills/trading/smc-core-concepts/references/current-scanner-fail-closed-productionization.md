# SMC current-scanner productionization and fail-closed data contract

Use when a historically strong SMC version is displayed as production but current picks are stale, empty, or derived from historical artifacts.

## Separate four physical truth layers

1. `historical_trades`: realized benchmark rows; may contain exit/PnL fields.
2. `current_seeds/current_candidates`: regenerated from the latest full-market raw K-lines; must not contain outcomes.
3. `shadow_candidates`: isolated research rows; always `shadow_only=true`, `buy_enabled=false`, `trade_action=NO_BUY` until separately promoted.
4. `positions/ledger`: actual execution state, populated only from current `BUY_VALID` rows.

A rematerializer that merely rewrites historical trades/picks is not a current scanner. Never use old active rows or historical winners as fallback supply.

## Data refresh must fail closed

Required sequence:

`provider fetch -> response validation -> atomic cache write -> freshness manifest -> scanner`

Hard requirements:

- Validate HTTP/body/schema before JSON parsing; HTML/WAF pages must have a stable source error classification.
- Write each cache through a temporary file followed by atomic replace.
- The refresh process exits nonzero if coverage/freshness gates fail.
- Daily ops must stop before selector, scanner, rematerializer, shadow audit, or ingest when freshness fails.
- Never replace a missing market date with the host's current date; report `DATA_UNAVAILABLE` instead.
- Preserve monitoring of already-open positions, but prohibit new buys.

Recommended full-market gate: requested universe is complete, successful fetch ratio >=98%, and latest-market-date coverage >=98%. Treat zero valid candidates after a successful scan as a legal empty-market state.

## BUY_VALID gate

Only current raw-scan rows may become production picks. At minimum require:

- freshness gate PASS and candidate `data_date == latest_market_date`;
- source kind is current raw scan, not historical/shadow/watch-only;
- semantic derivation is independently valid;
- ordered lifecycle: `event <= POI < touch <= reclaim <= confirmation < entry`;
- entry occurs after confirmation and A-share exits begin no earlier than T+1;
- valid geometry: `zone_low < zone_high`, `sl < entry < target`;
- no realized outcome fields;
- canonical `symbol + ontology + event + POI + lifecycle` identity is unique.

If no row passes, atomically write an empty current-picks array. Never lower the gate to manufacture activity.

## Apparent historical survivor correction

A walk-forward survivor is invalid if its rule uses takeover/hold features that become known after the replayed entry. For an `n`-bar post-reclaim confirmation, the first legal entry is:

`entry_idx = reclaim_idx + n + 1`

The V365 lineage is the reference regression case: all 402 apparent survivor rows entered 2-3 bars before their required confirmation; causal replay of 11,149 rows produced no surviving rule. Preserve this lineage as a quarantine/future-leak regression corpus, not as a shadow challenger or BUY source.

## Shadow challenger governance

Allow at most one active challenger. A candidate ontology must first prove it is causally distinct from closed parameter families, then pass:

1. full-universe no-outcome semantic generation;
2. independent event/POI/lifecycle rederivation;
3. at least 40 takeover seeds in every 2023-2026 year;
4. zero chronology and T+1 failures;
5. exactly one frozen replay with predeclared gates.

Failure closes the ontology. Do not answer failure with window, threshold, SL/TP, RR, or hold-period variants.

### Event identity must survive until execution dedup

Do not deduplicate event-anchored POIs by `ob_idx` before lifecycle evaluation. The same candle can be the nearest opposite-candle OB for multiple independently confirmed structure events; collapsing by OB index silently removes valid event identities. Preserve `(symbol, event_idx, poi_idx)` through lifecycle generation, then deduplicate only the final execution identity (for example `symbol + takeover_date`) under a documented deterministic tie-break. V434/V435 caught this as 79 independent-oracle mismatches; removing premature OB dedup changed unique Supply-Failure Breaker takeovers from 68,569 to 68,632 and reduced full-universe mismatch to zero.

Distinct local-daily ontology directions worth semantic admission testing include:

- **Supply-Failure Breaker:** pre-existing bearish supply is broken and role-reverses into support; this is not a Demand-OB retest. V434/V435 passed full-universe semantic and independent-oracle gates after removing premature OB-index dedup, but the one frozen V436 T+1 replay failed the predeclared economic gate: n=65,553, WR=73.4566%, AvgPnL=0.2963%; 2023 AvgPnL=-0.4471% and 2023–2024 epoch AvgPnL=-0.0443%. Close this ontology; do not create window/SL/TP/hold variants.
- **Target-First DOL:** an untouched external liquidity target is frozen before the event and governs the setup; it is not a post-hoc TP filter.
- **Protected-Swing Transfer:** control transfers through a causally visible protected swing and a newly protected low; it is not generic BOS/CHOCH relabeling.

## End-to-end verification

Before claiming production closure, verify the same version/date/source across summary, picks, live prices, monitor, K-line, analysis/docs, push, and closed-loop reports. Required invariants:

- current/list API contains no historical closed rows;
- shadow/quarantine rows leak into no production surface;
- current candidates contain zero outcome fields;
- T+1 violations are zero;
- data failure produces `NO_BUY` and no ingest;
- zero `BUY_VALID` produces a successful, explicit empty/flat state.

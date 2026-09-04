---
name: smc-strategy-research
description: Conduct causal, outcome-blind SMC strategy research with PIT events, fixed promotion gates, strict A-share T+1 execution, and fail-closed production isolation.
user-invocable: true
metadata:
  category: trading
  tags: [smc, strategy-research, pit-events, causal-validation, backtest, t-plus-one]
---

# SMC Strategy Research

Use for SMC strategy discovery, event-to-price causal research, strategy validation, and strategy promotion decisions. This is not a scanner or an execution skill.

## User objective and fixed gate

The objective is to discover a valid strategy, not to turn incomplete data into a reason to stop research. Use available 1–2 year data when necessary, label coverage honestly, and continue toward the strategy gate:

- total samples `>= 1,000`
- each available complete calendar year `>= 300`
- win rate `>= 55%`
- average net return `>= +0.50%`
- profit factor `>= 1.15`
- payoff `>= 0.70`
- average net return positive in every covered year
- strict A-share T+1 violations `= 0`

`EMPTY_BOOK` is a production safety state, not a reason to abandon legitimate research.

## Mandatory causal workflow

1. **Choose an independent ontology.** Do not re-mine a closed family with altered thresholds, windows, stops, targets, holding periods, years, or subsets. Prefer a genuinely independent PIT causal state or a new information dimension.
2. **Pre-register before reading outcomes.** State the event semantics, every causal node, time ordering, POI definition, entry, stop/target, T+1 handling, sample-support gate, and one-shot failure rule.
3. **Build outcome-blind seeds.** Read only event metadata and OHLC(V) through planned entry. Record source/event counts, seed counts, yearly counts, unique symbols, and causal-time invariants. Never read PnL, trade, exit, target, or outcome artifacts at this stage.
4. **Support failure closes before outcomes.** If support misses the fixed sample gate, close the ontology without loosening semantic filters or parameters. Retain its audit artifact and move to another independent source.
5. **If support passes:** run an independent raw-data identity oracle, then exactly one frozen strict-T+1 replay, then an independent metric audit.
6. **Production isolation.** Until every gate passes, write neither production candidates nor watchlists/frontend state. Historical trades never become live picks.

## SMC timing rules

- A swing high/low used as BSL/SSL must have completed its right-side confirmation before the break.
- A PIT event must be publicly available before its price response; do not use event day as response or entry unless publication time proves availability before the decision, which is normally avoided.
- Fix the POI before its retest.
- Enter only after every required confirmation; exits must begin at least the next eligible trading day.
- Resolve same-bar SL/TP collisions conservatively (stop first) and audit every exit date against entry date.

## Event-catalog workflow

For a new public-event class, first build a resumable, metadata-only catalog. Store only symbol, announcement ID, notice date, publication time, title, source coverage, and failed dates. Do not begin strategy semantic selection or price/outcome work until source coverage is recorded. Then pre-register one event semantic and run the outcome-blind seed gate.

See `references/pit-event-strategy-research-gate.md` for the concrete 2026 evidence and reusable implementation details.

### Source-universe and support-failure pitfalls

- **Coverage is scoped to its source universe.** Do not treat literal action phrases in an earnings-only archive as a complete company-action universe. Action sources require their own complete denominator, announcement/version identity, action-stage taxonomy, numeric-term/effective-date fields, and independent parser/oracle before semantic selection.
- **Distinguish closure layers.** Wrong source denominator = `CLOSED_SOURCE_CANDIDATE`; insufficient semantic events = `CLOSED_SEMANTIC_OBJECT`; insufficient valid outcome-blind chains = `CLOSED_ONTOLOGY_NO_REPLAY`; frozen replay failure = `CLOSED_NO_VARIANTS_NO_PRODUCTION`.
- **Never rescue a support failure.** Once a pre-registered PIT-to-SMC ontology misses its seed support gate, do not alter response/pivot/OB/touch/reclaim/hold windows, cache ranges, RR, stop, target, years, symbols, regimes, or old SMC labels. Do not inspect outcomes; move to another independent source.

See `references/pit-source-universe-and-preregistered-ontology-closure.md` for the source-contract checklist, closure taxonomy, and worked evidence.

## Reporting requirements

Report causal path, coverage years, event count, seed count, yearly seed count, unique symbols, invariant results, and the exact gate decision. Do not report attractive aggregate metrics as a substitute for mechanism validation. If an ontology is closed, say whether closure occurred at source support, oracle equality, replay economics, yearly stability, or T+1 compliance.

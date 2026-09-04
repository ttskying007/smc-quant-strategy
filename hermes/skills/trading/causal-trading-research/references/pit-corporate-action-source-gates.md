# PIT corporate-action source gates

Use this when a new trading cause is a timestamped announcement-body fact rather than price-only SMC.

## Required sequence

1. Freeze a metadata denominator by immutable `announcement_id`; deduplicate aliases without inflating coverage.
2. Fetch raw body by the same ID. Require payload ID and publication timestamp to equal metadata; retain a content hash.
3. For empty inline text, recover only the official attachment returned by that same payload and preserve attachment identity/hash. Do not cross-source stitch.
4. Audit 100% total and yearly raw-body coverage before defining a semantic field.
5. Pre-register a bounded body parser and an independent parser/Oracle. Require exact canonical-ID and numeric-field agreement.
6. Before reading price values, pre-register one causal ontology, same-date prohibition, observation start, response horizon, seed identity, pre-entry target/stop/RR, strict T+1 execution, fees, collision rule, time stop, and cross-year promotion gates.
7. Run a source-session audit first. It must prove every frozen event has the exact next eligible session and every session required by the declared response horizon. This audit should read only bar dates.
8. Only after source coverage passes: outcome-blind seed -> independent raw-bar Oracle -> exactly one frozen replay -> independent metrics -> separately specified scanner/UI isolation.

## Candidate-universe enumeration gate

Before collecting bodies or reporting a source-coverage percentage, prove how the source enumerates **all** action candidates. A title may locate pilot documents, but cannot establish a canonical denominator or become the action fact.

- Require a provider-declared action class, document taxonomy, instrument/action relationship, registry, or another title-independent enumerator.
- Generic announcement metadata (ID, date, title, generic source fields) cannot prove complete recall for a body term such as a convertible-bond conversion-price revision.
- If only title search is available, close that source candidate at the enumeration gate. Do not run a title-defined pseudo-full-universe crawl, infer absent terms from nonmatching titles, or advance to semantic extraction.
- Record this as a **source-enumeration failure**, distinct from body-transport failure and from later price-session coverage failure.

## Fail-closed rules

- Incomplete session coverage is a **source/time failure**, not evidence of no response and not an economic result. Close the ontology before seeds; do not drop older events, use a covered-only subset, extend the cache, switch provider, or alter the horizon to rescue it.
- Semantic support failure closes the exact semantic object before price data.
- Seed support failure closes the exact ontology before outcomes.
- Frozen replay failure closes the exact ontology; no post-hoc filters, response windows, POIs, stop/target/RR/hold changes, year subsets, or regimes.
- Current production stays `EMPTY_BOOK` until research, current raw scanner, freshness, and frontend/write-isolation gates all pass.

## Evidence pattern

A complete announcement-body archive can be source-qualified via same-ID text/PDF recovery and independent semantic parsing, yet a later strategy ontology can still correctly close before outcomes when the frozen event universe lacks exact session coverage. Historical ticks and PIT industry flow require their own raw-provider and point-in-time constituent qualification; price-derived industry proxies are not substitutes.

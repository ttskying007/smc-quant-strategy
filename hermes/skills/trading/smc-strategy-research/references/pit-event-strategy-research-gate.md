# PIT Event → SMC: session evidence and implementation notes

## Fixed research criterion

Use available 1–2 year data rather than stopping solely for incomplete history, but require: total samples >=1,000; each covered complete year >=300; WR >=55%; average net >=+0.50%; PF >=1.15; payoff >=0.70; every year average net positive; strict T+1 violations=0.

## Reusable execution pattern

- Pre-register the causal chain before reading outcomes.
- Generate seeds from PIT metadata plus OHLC(V) up through planned entry only.
- Verify: event < response < break/displacement < POI retest/reclaim < planned entry; BSL/SSL pivots need right confirmation before break; one seed per symbol+entry date.
- On support pass: independent raw oracle equality, then one frozen replay with next-session entry and earliest next-session exit.
- On support failure: do not inspect outcomes or alter the title rule, window, selector, stop, target, hold, years, or subset.

## Evidence: holder-demand commitment branch

A frozen outcome-blind ontology was tested on 2023–2025 local data:

`PIT HOLDER_INCREASE commitment -> confirmed external BSL close break -> last bearish demand OB -> retest/reclaim -> next daily open`

- eligible PIT events: 1,316 (2023:356; 2024:632; 2025:328)
- raw seeds: 1,059
- canonical seeds: 947 (2023:169; 2024:464; 2025:314)
- unique symbols: 619
- all causal-order and pivot-confirmation invariants: pass
- decision: support insufficient (total short by 53; 2023 short by 131); outcomes were not opened.

This preserves a useful distinction: shareholder *snapshot* features and announced shareholder *demand commitment* are different information states. The latter still failed only the pre-outcome support gate here; it must not be broadened retroactively to force a replay.

## New PIT category source-catalog pattern

For potential contract/award/order disclosures, a resumable catalog should query every calendar day, checkpoint completed and failed dates, and preserve only event metadata. Suggested metadata fields: symbol, announcement ID, notice date, publication time, title, matched semantic terms, source date. Build the catalog first; freeze event semantics later. This prevents title selection from being tuned after seeing price outcomes.

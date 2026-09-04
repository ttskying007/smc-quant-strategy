# HTF Trend → LTF Entry Support Gate

## Architecture correction

A low-timeframe setup must not decide both market direction and entry. Test the layered architecture explicitly:

`completed weekly parent trend → completed daily bridge trend → lower-timeframe entry lifecycle`

A weekly event followed by daily entry is **not** equivalent to a weekly/daily trend router followed by 15m entry. Likewise, an unconditioned 15m setup does not test the layered architecture.

## Outcome-blind contract

Before outcomes are opened:

1. Freeze parent trend definitions and lower-timeframe lifecycle parameters.
2. At every LTF entry, assert weekly and daily confirmation timestamps are strictly before the entry session. Never use entry-day daily close/high/low.
3. Pivots require their right-side confirmation; record confirmation time, not just pivot time.
4. Require strict LTF order: confirmed pivot/SSL → sweep → BOS/displacement → FVG/POI → first retest/reclaim → next executable bar.
5. Apply declared total-sample, per-year, and symbol-breadth support gates before Oracle or replay.
6. If support fails, close as `SUPPORT_INSUFFICIENT`; do not loosen trend definitions, windows, or volume thresholds to force outcomes.
7. Partial minute history is research-only. A later economic pass cannot authorize all-history production.

## V548 evidence

Sina source-isolated data over 5,528 symbols tested completed weekly HL+BOS and daily HL+BOS trend states before a 15m `SSL → high-participation sweep → displacement BOS/FVG → low-participation reclaim → next-bar` entry identity.

- 220 outcome-blind identities, 201 symbols
- 2025: 61; 2026: 159
- Contract: total >=300 and each year >=80
- Timestamp order, parent-before-entry, no-outcome-field, and no-write assertions passed.

It closed at support gate without reading outcomes, Oracle, or replay. This is a support failure—not an economic failure—and is the correct fail-closed handling for a plausible new MTF ontology under partial 15m history.

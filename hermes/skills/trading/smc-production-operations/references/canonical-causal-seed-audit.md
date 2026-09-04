# Canonical causal seed audit

## Why this exists

A legacy candidate stream can overstate signal supply even without explicit future leakage. Two semantic defects are especially dangerous:

- emitting a BOS on every later bar that remains above an old swing high;
- assigning an OB by scanning arbitrary candles forward instead of locating it backward from the actual break.

Both create labels that look structured but do not represent a unique causal event.

## Required raw-bar contract

For a bullish continuation seed:

1. A 3-left/3-right swing high is valid only after its right confirmation bars complete.
2. BOS is a unique crossing: previous close `<= pivot_high`, current bullish close `> pivot_high`.
3. If a bar crosses multiple known highs, record the chosen structural anchor but consume all crossed pivots; none may trigger again after a retracement.
4. Find the nearest bearish candle in the fixed pre-BOS lookback. Its low/open define the demand zone.
5. After BOS: zone touch must occur without a close below zone low; a later close must reclaim above zone high; a still later bar must hold above zone high with low above zone low; entry is only the next session.

## Audit scope

Validate every emitted seed directly against raw bars, not merely a random sample. Report:

- checked seed count and symbol count;
- confirmation, first-crossing, OB-provenance, zone-price, lifecycle-order, and next-session-entry checks;
- count of any `pnl`, `return`, `exit`, `target`, or `stop` seed fields (must be zero);
- explicit `production_write=false`, `watchlist_write=false`.

Only a zero-failure audit authorizes a single frozen strict-T+1 replay. A replay failure closes that exact ontology; do not use thresholds, exits, time windows, symbol subsets, or calendar slicing to rescue it.

## Session validation example

A full-universe daily reconstruction produced 49,256 outcome-blind canonical continuation seeds across 4,887 symbols. The raw-bar semantic audit checked all 49,256 and found zero violations for pivot confirmation, first BOS crossing, backward-OB identity, zone prices, lifecycle ordering, next-session eligibility, and outcome-field exclusion. This demonstrates semantic validity only; it is not evidence of economic profitability or production eligibility.

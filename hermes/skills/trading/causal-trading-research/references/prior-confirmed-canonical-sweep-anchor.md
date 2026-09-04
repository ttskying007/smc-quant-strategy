# Prior-confirmed canonical SSL Sweep anchor

Use when a scanner/replay claims to use a confirmed Swing Low but derives its anchor from a fixed relative bar position.

## Semantic contract

For candidate Sweep bar `i` with right-side confirmation `R`:

1. Enumerate every Swing Low `j` satisfying `j + R < i`; confirmation must be complete before the Sweep.
2. Exclude `j` if any bar from `j + R + 1` through `i - 1` has `low <= swing_low`; the liquidity was already consumed and cannot be reused.
3. Retain lows actually pierced by the candidate bar at the predeclared breach and reclaimed by that bar's close.
4. If several qualify, select the nearest prior (`max(j)`) deterministically; persist both the rule name and qualifying-anchor count.
5. Persist `swing_date`, `swing_confirm_date`, `swing_to_sweep_bars`, `sweep_date`, `response_date`, and entry-eligible date. Never label a fixed candidate-evaluation date as a realised Sweep date.

## Fixed-offset trap

`j = i - R - 1` is **not** “a prior confirmed Swing Low.” It requires the Sweep exactly one bar after confirmation and causes systematic false negatives. It can also make dashboard Swing/Sweep dates appear mechanically synchronized.

## Repair protocol

A semantic anchor repair invalidates all downstream artifacts. Rerun in order:

1. result-blind seed generation;
2. independent raw-bar Oracle over full causal identities;
3. one frozen strict-T+1 replay;
4. independent metric audit only if the replay clears all declared gates;
5. scanner-time materialization plus frontend anchor provenance.

No threshold/window/SL/TP/holding-period/year/subset variants are allowed as compensation. A repaired ontology that fails a declared frozen gate is closed and `EMPTY_BOOK` remains in force.

## Mandatory assertions

- `swing_idx + R < sweep_idx < response_idx < entry_eligible_idx` for every seed;
- generator and Oracle identity sets exactly match;
- zero A-share same-day exit violations;
- current scanner observations remain non-executable until independent release and exact-next-open checks pass;
- the frontend calls its early funnel stage a visible/unmitigated anchor, not a completed Sweep.

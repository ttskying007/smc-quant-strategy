# V365–V368 Causal Re-entry Closure

Use when a daily SMC candidate appears to pass a historical or walk-forward gate after a reclaim/takeover confirmation layer.

## Non-negotiable causality rule

If `TRUE_TAKEOVER_n` relies on the `n` bars after reclaim, entry cannot occur before:

`entry_idx = reclaim_idx + n + 1` (the next bar's open).

The old source-row entry may be used only if it is at or after this index. Otherwise its outcome is future-data contaminated.

## V365 apparent survivor: invalid

V365 found a common OOS rule on V333:

`v164 & industry & bull3_ge3 & zone_ge2 & ob_or_obfvg`

But V366 checked its 402 candidate rows and found all entries occurred before their required confirmation:

| Check | Result |
|---|---:|
| entry before confirmation-2 | 402/402 |
| entry minus confirmation-2 | -2 bars |
| entry before confirmation-3 | 402/402 |
| entry minus confirmation-3 | -3 bars |

Therefore V365 metrics must never be used for promotion.

## Correct causal rebuild

V367 replayed all V164-eligible historical rows at the actual confirmation-next-open:
- strict takeover-3 → reclaim + 4 open
- otherwise takeover-2 → reclaim + 3 open
- exit uses the V132 delayed semantic model and is strictly T+1.

Predeclared unchanged gates:
- Dev: `n>=120`, per-year `n>=40`, WR `>=90%`, AvgPnL `>=7%`, min-year WR `>=88%`, micro `<=1%`, T+1=0.
- OOS 2025–2026: same with `n>=100`.
- OOS 2026: same with `n>=40`.

### Result

| Item | Result |
|---|---:|
| causal replay rows | 11,149 |
| overall WR | 41.5104% |
| AvgPnL | 1.8322% |
| WF-A development survivors | 0 |
| WF-B development survivors | 0 |
| common OOS survivors | 0 |
| T+1 violations | 0 |

V368 independently recalculated every row's `reclaim_idx + n + 1`, K-line entry date/open and exit order: 11,149 rows, 0 mismatches, 0 same-day exits.

## Decision

Close the V164/V132 daily rule-mining route. Do not compensate with more daily scalar gates: after the causal entry correction, no rule comes close to the predeclared gate.

The next genuinely new direction is complete 2023–2026 intraday history, followed by an intraday POI reaction generator and the same causal + walk-forward gates. Current M60 cache cannot validate that route historically.

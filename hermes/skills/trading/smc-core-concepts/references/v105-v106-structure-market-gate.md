# V105/V106 Structure-Market Gate Lesson

Use this reference after a strict `touch -> reclaim -> next-open entry` rebuild passes semantic gates but still fails production quality.

## Core Lesson

A reclaim-order repair can be correct while the strategy remains non-promotable. Do not keep optimizing TP/SL to force headline WR. Separate:

1. **Semantic validity** — `touch_idx <= reclaim_idx < entry_idx`, no same-day exit, no pollution.
2. **Structural trading validity** — TP/SL must remain SMC structure-based; micro-profit exits do not qualify.
3. **Market regime validity** — signals must only fire in ex-ante tradable environments.

## V105 Pitfall: Micro-Profit False Pass

In V105, the best statistical matrix used:

- `tp_rr = 0.6`
- `sl_buf = 0.75`
- `max_hold = 13`

This produced WR > 70% and lower SL rate, but it is **not promotable** because `0.6R` is a micro-profit exit, not an SMC structural target. If `TP_R >= 1` has zero qualifying candidates, report the matrix as a rejected diagnostic, not an upgrade.

## V106 Correct Follow-Up

After rejecting micro-profit tuning, return to original structural TP/SL and test signal/environment gates only.

Useful ex-ante diagnostics:

- `retrace_pct` bands, especially `10–50`.
- `risk_pct` bands; prior results showed risk `3–5%` as a higher-quality subpool but sample-limited.
- Market breadth on the entry date computed from raw K-line universe:
  - percent above MA20 / MA60
  - average 20-bar and 60-bar return
  - positive ret20 / ret60 ratio

Example V106 finding with original structural exits:

| Gate | n | WR | SL | Avg | Stable months |
|---|---:|---:|---:|---:|---:|
| `retrace_pct 10–50`, risk<=8 | 203 | 62.07% | 36.45% | 1.2962% | 7 |
| market up20>=35%, up60>=30%, avg_ret20>=-2%, retrace 10–50, risk<=8 | 150 | 68.00% | 30.67% | 2.0879% | 7 |

This is improved but still below promotion gates (`WR>=70`, stable months>=12). The correct conclusion is **do not promote; rebuild market-state layer**.

## Reporting Pattern

For Lei, report compact tables:

- baseline semantic gate status
- best structural signal gate
- best market-regime gate
- yearly breakdown, especially whether weak years such as 2024 are fixed or merely excluded
- explicit non-promotion reason

Avoid presenting micro-profit results as a candidate system. State that they are diagnostic only.

## Next Valid Direction

Build a dedicated `TRADEABLE_REGIME` layer from ex-ante market breadth + SMC structure, then rerun full-market backtest from raw K-lines. Do not connect to production until semantic, monthly stability, and structural TP/SL gates all pass.
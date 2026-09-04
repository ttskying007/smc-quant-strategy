# PIT Context & Full-History Intraday Research Gates

Use this when an SMC branch has correct causal semantics but poor realised quality, and the next hypothesis needs historical intraday or external context.

## Non-negotiable sequence

1. **Freeze semantic detector first.** Independently re-derive pivots, structure breaks, OB anchors, sweeps and FVG geometry. Require zero differential mismatches and explicit causal visibility before any execution test.
2. **Pass the data gate before modelling.** For intraday OHLCV, account for every symbol; require exact expected session slots, quarantine source anomalies, reset daily detector segments at gaps, and never mix legacy adjusted daily prices into a raw-source experiment.
3. **Build a fully specified replay.** Write entry, target, stop, same-bar collision ordering and A-share T+1 rules before looking at outcomes. Enforce serial per-symbol execution where positions would overlap.
4. **Evaluate the base mechanism before filters.** A context label cannot rescue a structurally losing generator. Close the branch if the fully causal replay fails its fixed production gate.
5. **Test new context outcome-blind.** Build PIT features using only information available at or before the confirmation/hold timestamp; confirm coverage and cutoff equality before joining with results.
6. **Use fixed gates; do not tune after results.** A research context needs broad sample size, per-year coverage, economic uplift, and chronological stability. A strong aggregate with thin boundary years is research-only.

## Reference production gate

For a candidate intended to replace or augment a production SMC path, predeclare and require all of:

| Requirement | Threshold |
|---|---:|
| Total closed sample | >=300 |
| Each validation year | >=40 |
| Net WR | >=87% |
| Avg PnL | >=6.8% |
| Minimum yearly WR | >=84% |
| Micro-profit share | <=1% |
| A-share T+1 violations | 0 |

For a **context discovery** layer over a fixed baseline, require: each-year n>=40, WR uplift>=5pp, AvgPnL uplift>=1pp, minimum-year WR uplift>=3pp, plus chronological walk-forward stability. Passing only some conditions means no promotion.

## PIT disclosure pattern

- Provider publication timestamp (`eiTime`), not notice date, is the availability field.
- Query and enforce the exact interval `[hold_time - N calendar days, hold_time]` per symbol/candidate. A cache populated for a larger request scope can silently contaminate the lower time bound.
- Freeze title taxonomy before outcomes and preserve priority ordering (negative/regulatory first, then capital return, fundamentals, business, other/no event).
- A small outcome-positive bucket must be rechecked with predeclared chronological slices and nested, predeclared event windows (for example 1/3/5/10/20 days). These tests are robustness evidence, not a window-selection search.

## Empirical session lesson (2026-07)

A raw-source full-market 60-minute rebuild made 2023-2026 MTF validation feasible and semantic parity passed, but the true daily-POI -> 60m touch/reclaim/hold replay was decisively unfit for production (n=4,832, WR=35.39%, AvgPnL=-0.1562%, SL=56.91%, T+1=0). Whole-market participation and behavior-cohort context added insufficient information. Exact five-day PIT `FUNDAMENTAL_POSITIVE` disclosure context showed a real association (n=257, WR=47.47%, AvgPnL=+1.2354%, SL=42.02%) and positive 2024-2026 directional walk-forward uplift, but failed sample/coverage gates (notably 2026 n=29). It remains a non-promotable research signal.

## Pitfalls

- Do not declare a signal correct because its backtest is good; semantic differential parity and causal visibility are separate gates.
- Do not call a feature PIT merely because the upper timestamp is bounded; verify the exact lower bound for every candidate.
- Do not promote an effect whose best-looking year is underpowered.
- Do not use a context filter to hide a base generator that fails its own mechanism-level gate.
- Do not reopen closed scalar-gate, exit-only, or broad daily-supply searches without genuinely new information content.

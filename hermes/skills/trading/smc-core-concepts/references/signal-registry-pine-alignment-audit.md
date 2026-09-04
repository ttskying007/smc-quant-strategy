# SMC Signal Registry and Pine-alignment audit

Use this reference when auditing or repairing an SMC engine after the user says K-line signals are inaccurate, asks whether every SMC signal is Pine-aligned, or reports that backtest/selection/chart/replay surfaces disagree.

## Core lesson

Do not say “SMC signals are Pine-aligned” from aggregate WR/RR. Pine alignment is family-by-family and source-by-source. A high-win-rate mixed engine can still be visually wrong on the K-line chart.

Typical mixed-engine risk:

```text
BOS / CHOCH / MSS / Sweep / OB  -> LuxAlgo-style core
FVG / EQH-EQL / BPR / OTE / LV  -> Pine-like/local core
Entry / exit / market_state     -> older engine helpers
K-line frontend                 -> merged signals_list from several sources
```

If this pattern exists, report it explicitly as “mixed source / not single Pine script aligned”.

## Required SignalRegistry table

For the active version, build or report a table like this before editing logic:

| family | active source | reference Pine/script | trading-consumed? | chart-visible? | expected params | severity if mismatched |
|---|---|---|---|---|---|---|
| BOS/CHOCH | LuxAlgo currentLevel / Waves / Pine-like | LuxAlgo or user Pine | yes/no | yes | swing len, close/wick break, ATR penetration | P0 |
| MSS | independent internal MSS vs CHOCH-attached MSS | LuxAlgo/Pine semantics | yes/no | yes | early vs confirmed split | P0 |
| Sweep | pivot/currentLevel/EQH-EQL pool | user Pine liquidity sweep | yes/no | yes | lookback, cooldown, pool density | P0 |
| OB | wave-aligned + displacement / SMC2026 OB | user Pine OB settings | yes | yes | swing len, lookback, displacement, wave distance | P0 |
| FVG | Pine-like 3-candle gap | user Pine FVG settings | yes/no | yes | gap rule, ATR mult, mitigation touch/fill | P0 |
| EQH/EQL | Pine-like/local | user Pine EQ settings | maybe | yes | threshold, pivot len | P1 |
| BPR/BRK/RB/LV/OTE | local reference layer | none unless proven | usually no | optional | source_layer=experimental/reference | P1 |
| Pinbar | confirmation only | local/Pine candle rule | confirmation only | optional | strict wick/body rule | P2 |

Persist this registry in metrics or diagnostics so the frontend and reports cannot silently mix semantics.

## Known severe mismatch patterns

### Sweep overproduction

If Lux-style sweep counts are tens per symbol while Pine-like/reference sweeps are only a few per symbol, treat as P0. Common causes:

- `lookback` too large (e.g. 80 bars)
- no per-direction cooldown
- repeated sweeps of old `currentLevel` pivots
- no liquidity-pool clustering or density requirement

Fix pattern:

```text
1. Reduce sweep lookback to recent actionable pools (often ~30 bars for daily A-share scans).
2. Add same-direction cooldown, typically 3 bars.
3. On the same bar/cluster, keep only the deepest penetration.
4. Prefer EQH/EQL or clustered liquidity pools over isolated stale pivots.
5. Store swept_idx/swept_label/pool_density for chart audit.
```

### MSS semantics collapsed

Do not permanently disable all CHOCH-attached MSS just because early MSS was noisy. Split fields:

```text
is_mss = early visual/diagnostic structure shift
is_mss_confirmed = tradable MSS after displacement/body/reclaim confirmation
```

K-line can display early MSS; trading should consume only confirmed MSS. Store reject reasons.

### OB not truly Pine-aligned

Wave anchoring improves OB but is not identical to user Pine OB unless parameters are replicated. For Pine-style OB audit, verify:

```text
ob_swing_len / OB Swing Detection Length
ob_lookback
OB Displacement Multiplier
minimum strength filter
wave_turn_label in valid side set
wave_turn_distance <= allowed window, commonly 3 bars
```

For long OB, valid wave labels are usually `HL`, `LL`, or initial `L`. For short OB, valid wave labels are `HH`, `LH`, or initial `H`.

### FVG mitigation mismatch

Explicitly separate raw gap detection from mitigation mode:

```text
raw bull FVG: low[i] > high[i-2]
raw bear FVG: high[i] < low[i-2]
profile fields: atr_mult, min_gap, require_prev_close, mitigation_mode=touch|50_fill|full_fill
```

If the strategy says “Touch” but code labels/uses “50% Fill”, this is a semantic bug even if metrics are good.

### EQH/EQL label drift

Frontend/API labels must preserve semantics:

```text
EQH -> EQH_High
EQL -> EQL_Low
```

Do not label equal highs as `EQL_High`.

## Trade autopsy required after signal changes

After any signal-definition change, rebuild trades/watchlist and compute at least:

```text
entry_zone_pos = (entry - zone_low) / (zone_high - zone_low)
MFE before exit
MAE before exit
post-exit MFE window, e.g. +30 bars
fake_sl = SL exit followed by large post-exit MFE
sold_early = exit followed by materially larger post-exit MFE
MFE capture = realized pnl / max(MFE, tiny)
```

Interpretation:

- `entry_zone_pos` near `1.0` means entries are at zone high; WR can remain high while RR is compressed.
- high `sold_early_rate` means TP/trailing is exiting before trend continuation; use structure-runner logic.
- high `fake_sl_rate` means structural SL may be capped into a fixed-percent SL or entry is too high.

## Reporting standard

For this user, the report must include:

1. Active code path per signal family.
2. Pine/reference mismatch by family with severity P0/P1/P2.
3. Whether chart signals, watchlist, trades, and replay are using the same source.
4. Per-bucket trade autopsy: entry quality, SL cause, TP reasonableness, early-exit evidence.
5. Frontend sync status: API fields, K-line markers, wave layer, trade overlays.
6. A concrete repair order; do not present choices for the user to pick.

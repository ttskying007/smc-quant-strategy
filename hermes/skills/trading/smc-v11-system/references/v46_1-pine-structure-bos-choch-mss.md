# V46.1 Pine-structure alignment: BOS / CHOCH / MSS review and repair

Use this reference when SMC users report that BOS/CHOCH/MSS are too few, visually inaccurate, or not matching Pine/LuxAlgo structure labels.

## Durable finding

The failure mode is usually not a single WR/RR parameter. Treat it as a full signal-definition and synchronization problem:

1. **Structure scale too coarse**
   - Pine screenshot/reference settings used `Swing Length 5`.
   - Existing LuxAlgo-style core had used `swing_len=20`, which suppresses BOS/CHOCH/MSS density.
   - Empirical sensitivity on 120 symbols showed approximate average MSS per symbol:
     - `swing_len=20 -> 1.45`
     - `swing_len=10 -> 3.58`
     - `swing_len=7  -> 5.58`
     - `swing_len=5  -> 7.49`
   - After switching to `swing_len=5`, full-market structure audit remained valid: `bad_events=0`.

2. **MSS definition too strict**
   - Pine/LuxAlgo-style MSS behaves more like an early-warning market structure shift, not only a fully confirmed reversal.
   - Do not replace CHOCH with MSS. Render CHOCH, and when qualified, also render an MSS marker at the same event.
   - Recommended split:
     - `is_mss`: early-warning MSS, e.g. CHOCH with recent opposite-side liquidity sweep.
     - `is_mss_confirmed`: stricter trade-quality flag, e.g. early MSS plus displacement/body confirmation.
   - Display/K-line can use `is_mss`; reversal trade gating should usually prefer `is_mss_confirmed` or an explicit stronger condition.

3. **Output-chain filtering loses structure**
   - Keep both `swing_structure` and `internal_structure` in signal outputs when available.
   - The K-line API should expose BOS, CHOCH, and MSS markers from the same core used by backtest. Do not let frontend show a different structure engine than backtest.

4. **Frontend sync must be verified, not assumed**
   - Run `/api/reload` and then check `/api/picks`, `/monitor`, and `/api/kline_full?symbol=...&tf=daily&ver=V46_1`.
   - Healthy K-line response should include `signals_list` families such as `bos`, `choch`, `mss`, `ob`, `fvg`, and a non-empty highlight chain when the symbol has an active setup.
   - Verify `pick_scope == ACTIVE_CANDIDATE`, `is_active_pick == true`, TP/SL/quality fields populated, and K-line highlights use `source_event_idx -> zone_idx -> retrace_index -> conf_index`.

## Code-level repair pattern

Primary files:

- `/root/.hermes/scripts/v25/smc_core_luxalgo_v34.py`
- `/root/.hermes/scripts/v25/v34c_next_open.py`
- `/root/.hermes/scripts/v25/v46_1_layered_3y.py`
- `/root/.hermes/scripts/smc_unified.py`

Steps:

1. **Align structure scale**
   - Set LuxAlgo structure detection default/call-site to `swing_len=5, internal_len=5` when matching the user-provided Pine screenshot/profile.

2. **Split MSS semantics**
   - In `qualify_mss()`, keep `is_mss` as the broader early-warning flag.
   - Add `is_mss_confirmed` for the old strict condition.
   - Preserve `mss_reason` so autopsy can explain whether the marker is early-only or confirmed.

3. **Separate display semantics from trade gating**
   - K-line/analysis/front-end structure markers may render all `is_mss` events.
   - Reversal setups that require a strong reversal should use `is_mss_confirmed` or an explicit `strong_mss` predicate. Do not silently let a display-semantic broadening weaken trade filters.

4. **Rebuild and audit before interpreting WR/RR**
   - Re-run the full market rebuild, not a sample-only run:
     - `cd /root/.hermes/scripts/v25 && python3 v46_1_layered_3y.py --rebuild-base`
   - Run/inspect structure audit and require `bad_events == 0`.
   - Compare event density, not only trade metrics.

5. **Autopsy after rebuild**
   - Check problem buckets such as:
     - `LIQUIDITY_TARGET_TOO_CLOSE_OR_MISSING`
     - `CONFIRM_NOT_TWO_BAR_REJECTION_HOLD`
     - `OB_NOT_VISUAL_SMC2026_ZONE`
     - `REVERSAL_NO_STRONG_MSS`
     - `FVG_NOT_PINE_PARAM_OR_BOUNDARY_SHIFT`
     - `FVG_TOO_WIDE`
   - These indicate remaining Pine boundary/zone-quality debt, not merely stop-loss issues.

## Verification checklist

Minimum final report should include:

- BOS / CHOCH / MSS counts before and after.
- Trade count, WR, SL rate, and RR/avg PnL before and after.
- Full-market structure audit: total events, `bad_events`, and top event counts.
- Example per-trade rows with `entry_date`, `entry_price`, `exit_price`, `exit_reason`, `conf_type`, `source_event`, `zone_type`, and autopsy issues.
- Frontend checks:
  - `/api/reload`
  - `/api/picks`
  - `/monitor`
  - `/api/kline_full?...ver=V46_1`
- Clear statement of whether Pine alignment is complete. If OB/FVG boundary issues remain, say it is only partially aligned.

## Pitfalls

- Do not claim “Pine aligned” just because WR improved or structure audit passed. Audit passing only proves invariants; visual Pine alignment also needs correct OB/FVG boundaries and display synchronization.
- Do not collapse `CHOCH` into `MSS`; Pine-style charts commonly show structure labels and early warning markers as related but distinguishable layers.
- Do not validate by one symbol only. Use one symbol for K-line API smoke test, but full-market audit/backtest must remain the acceptance gate.

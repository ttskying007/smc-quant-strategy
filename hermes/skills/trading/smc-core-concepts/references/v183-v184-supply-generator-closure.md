# V183-V184 post-V175 supply generator closure

Date: 2026-06-25

## Trigger

Use when continuing SMC research after V175/V180-V182 closure and considering whether the next improvement can come from a new raw-signal generator or from old V85 high-WR supply.

## Gates used

Production upgrade usable:
- non-leaking source-side rule;
- T+1 violations = 0;
- combined engine `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API mutation before dry-run passes.

Research child engine usable:
- 100% non-overlap vs V175;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

## V183 — raw Pine-like classical sweep→CHOCH→OB generator

Artifact: `/root/.hermes/smc_audit/v183_classical_sweep_ob_generator_20260625_131931/`

Generator contract:
- source is raw K-line cache + `smc_core_pine_like_v32a`, not V128/V167/V172/V175 filtering;
- detect classical bullish SSL sweep, then bullish CHOCH/MSS, then Pine-like OB from the CHOCH break;
- require later OB touch and later reclaim bar; same touch bar cannot self-confirm;
- entry at next open with chase <= 3%; risk bounded 1.5%-8%; planned target is prior BSL swing high with 1.5R fallback;
- replay enforces T+1 by construction; audit-only, no frontend/watchlist/API write.

Result:
- `symbols_scanned=4650`, candidates `n=63`, `overlap_with_v175=0`, T+1 violations `0`.
- Metrics: `WR=30.16%`, `Avg=-0.1649%`, `min_year_n=3`, `all_year_wr_min=21.62%`.
- Exit mix: `POI_CLOSE_BREAK=21`, `SL=17`, `GAP_SL=2`, `TIME=15`, `TP=8`.
- Decision: `FAIL_NO_WRITE`.

Interpretation:
- Strict textbook SSL sweep→CHOCH→OB is too sparse and weak on A-share daily data.
- Failures are not caused by T+1 or field pollution; they are semantic failures after reclaim (`POI_CLOSE_BREAK + SL/GAP_SL = 40/63`).
- Do not promote “classical purity” as a production direction just because it sounds more correct than V175 semantic split.

## V184 — V85 old high-WR supply runner frontier

Artifact: `/root/.hermes/smc_audit/v184_v85_runner_frontier_20260625_132418/`

Purpose:
- Test whether old V85 high-WR/low-Avg supply (`559`, originally WR ~89%, Avg ~2.71%) can become a V175-compatible child engine through executable runner exits.
- This is not a new production write; it is shadow-only replay.

Variants tested:
- `base`, `close_5d`, `close_10d`, `close_20d`, `close_40d`, `trail_after_1r_20d`, `trail_after_2r_40d`.

Key results:
- All variants have `overlap_with_v175=0` and T+1 violations `0`.
- No variant passed the V180 production upgrade gate.
- `base` child: `n=559`, `WR=78.53%`, `Avg=2.4255%`, `yearWRmin=73.64%`, `micro=9.12%`; combined with V175: `n=806`, `WR=80.15%`, `Avg=3.536%`.
- Longer fixed runners raise Avg slightly but destroy WR/year stability:
  - `close_40d` child `WR=26.3%`, `Avg=3.3655%`; combined `WR=43.92%`, `Avg=4.1879%`.
- Trailing runners create massive SL/trail/micro pollution and fail Avg/WR.

Interpretation:
- V85 remains a short-horizon micro-profit engine, not a V175-grade supply child.
- Runner exits cannot rescue it: the POI/risk geometry was built for quick liquidity-target wins, not trend capture.
- Do not combine V85 with V175 under the current production gate.

## Closed paths after V183-V184

Closed in addition to V180-V182:
1. Raw strict classical SSL sweep→CHOCH→OB daily generator.
2. Old V85 high-WR supply as a V175 child engine.
3. Generic fixed-day or simple trailing runner exits for V85.

## Next valid research direction

The remaining path is not more filtering or runner overlays. It must change the supply-generation premise:

- Build a source-side generator that first proves post-reclaim institutional takeover before entry, not after exit.
- Required pre-entry features should be available at entry time only: e.g. reclaim hold quality, micro higher-low after touch, relative zone compression/expansion, source-event displacement, broad environment permission, and pre-entry target geometry.
- Any MFE/MAE/exit_reason/realized pnl feature is diagnostic only and cannot be used as a selector.
- Start shadow-only; use V175 overlap checks and T+1 audit before any frontend/watchlist/API mutation.

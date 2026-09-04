# V38 Pine Gap Closed Signal Audit (2026-05-23)

## Trigger
User required all previously open P1-P4 issues fixed: missing BRK/RB, EQL/EQH not merged into sweep source, BPR/LV/OTE validation, frontend/K-line sync, rerun support, and trade quality protection (WR + payoff).

## Durable lessons

1. **Do not equate implemented signal definitions with tradable signals.**
   - V38 implemented/displayed BRK, RB, BPR, LV, OTE and merged EQL/EQH into sweep source.
   - Candidate all-signal trading failed quality gate, so those signals remain display/audit-only.
   - Formal promotion requires full-market evidence, not conceptual correctness.

2. **K-line marker source must match active trade core.**
   - For V38/V37/V36/V34D, K-line BOS/CHOCH/MSS/SWEEP/OB markers use LuxAlgo same-source core.
   - FVG/BPR/EQL/LV/OTE/BRK/RB are from the Pine-like display/audit core.
   - If K-line markers are not synchronized, users will correctly detect chart/trade inconsistency.

3. **EQL/EQH are not just markers; they must feed sweep source if enabled.**
   - V37 displayed EQL/EQH but did not use them as sweep source.
   - V38 merges Pine EQL/EQH sweeps with LuxAlgo swing sweeps, deduped by `(index, subtype/direction)`.

4. **BRK/RB implementation pattern.**
   - BRK = failed OB breaker block: former bearish OB closed above => bullish breaker; former bullish OB closed below => bearish breaker.
   - RB = rejection block from sweep rejection candle body/wick zone.
   - Both are valid for display/audit; they require additional filters before trading.

5. **Quality gate before promotion.**
   - V38 all-signal candidate: 20 trades, WR 65.0%, SL 25.0%, avg PnL +0.74%.
   - Failed cohorts: BRK 4 trades / WR 50% / SL 50% / avg -1.62%; LV 3 trades / WR 0% / SL 66.7% / avg -2.32%.
   - Final V38 promoted only OB/FVG: 12 trades, WR 83.3%, SL 8.3%, avg PnL +2.15%.

## Files touched in session

- `/root/.hermes/scripts/v25/smc_core_pine_like.py`
  - Added `breaker_blocks_from_obs()` and `rejection_blocks_from_sweeps()`.
  - Added `breakers` and `rejection_blocks` to `detect_all_signals_pine_like()` output.
- `/root/.hermes/scripts/v25/v38_engine.py`
  - Candidate all-signal audit engine; output under `/root/.hermes/smc_opt_v38p/`.
- `/root/.hermes/scripts/v25/v38_final_engine.py`
  - Final promoted engine; output under `/root/.hermes/smc_opt_v38/`.
- `/root/.hermes/scripts/smc_unified.py`
  - ACTIVE_VERSION priority updated to V38.
  - Rerun engine map supports V38/V37/V36/V34D.
  - K-line version selector/default and marker families updated.

## Verification pattern for future sessions

Run full-market engine, then verify frontend API and K-line marker families:

```bash
cd /root/.hermes/scripts/v25
python3 v38_final_engine.py --start-date 20250101
```

Expected final V38 quality baseline:

```json
{
  "n_trades": 12,
  "wr": 83.3,
  "sl_rate": 8.3,
  "avg_pnl": 2.15,
  "signals": {"OB": 7, "FVG": 5}
}
```

API sanity checks:

```text
/api/summary -> total_trades=12, win_rate=83.3, avg_pnl=2.15
/api/kline?symbol=001872.SZ&tf=daily&ver=V38 -> families include bos,bpr,brk,choch,eql,fvg,lv,mss,ob,ote,rb,sweep
```

## User-facing discipline

For Lei SMC work, report the exact status split:

- implemented/displayed/audited signals
- promoted trading signals
- failed candidate cohorts with metrics

Never say “all fixed” if it only means “definitions added”; promotion requires quality-gated full-market evidence.

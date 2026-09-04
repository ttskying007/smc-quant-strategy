# V70 90% WR Signal-Gate Pattern (Session 2026-06-12)

Use when Lei rejects a high-volume SMC candidate because WR is below the explicit target (e.g. “胜率依然太低，不满足90%”) and asks for signal-layer / strategy-wide repair rather than SL/TP tuning.

## Trigger

- Current strict L→D/FVG candidate has positive expectancy but WR is far below target (V68 example: 5,546 trades, WR 58.17%).
- SL autopsy shows many losses are not noise stops but invalid demand zones.
- User asks to iterate WR to 90%+ from signal layer and missing strategy checks.

## Mandatory Diagnostic Sequence

1. **Do SL autopsy before tuning**
   - Classify each SL_HIT using cached K lines:
     - `ZONE_DEAD`: exit bar close below zone_low.
     - `CLOSE_THROUGH`: exit bar close <= SL.
     - `WICK_STOP`: low <= SL but close > SL.
     - `GAP_THROUGH`: open < SL.
     - `RECOVERED_TO_TP`: after SL bar, original TP is hit within remaining hold window.
   - If `ZONE_DEAD` dominates, do **not** keep adjusting SL/TP. The signal layer is admitting dead demand zones.

2. **Run entry/SL/TP matrix to prove tuning ceiling**
   - Keep one unique setup per L→D opportunity.
   - Compare executable entries: `reclaim_close`, `zone_high_limit`, `zone_mid_limit`.
   - Compare SLs: current POI, sweep low, swing low.
   - Compare TPs: RR0.8, RR1.0, BSL, hybrid.
   - If best matrix WR is still <90%, the fix must be signal gates, not trade management.

3. **Add non-leaky signal/regime gates**
   - Use only information known before entry (typically prior close for market/stock context).
   - Candidate gate families:
     - Market breadth: % stocks above MA20/MA60 (computed prior bar).
     - Market return context: avg 5/20 day market return.
     - Stock context: stock above MA20/MA60, positive 5/20 day return.
     - Zone quality: narrow zone width.
     - Liquidity quality: sweep pierce ATR threshold.
     - Risk band: avoid too tight and too wide SL.
   - Treat these as **regime/quality gates**, not SMC signal definitions. SMC event sequence remains the trade premise.

4. **Promotion gate**
   - Do not promote a 90%+ subset if it is too sparse or concentrated in one year.
   - Required before production:
     - Full-market run.
     - WR >= target.
     - Prefer n >= 100–200.
     - T+1 failures = 0.
     - Semantic order failures = 0.
     - Field contract failures = 0.
     - Year/regime robustness; not only one favorable period.
     - Current picks must not be historical trades disguised as active candidates.

## Proven V70 Precision Candidate (Research Only)

V70 found a 90%+ research subset, but it was **not production-promoted** because sample size and year robustness were insufficient.

Gate:

```text
market MA20 breadth: 50% - 65%
market MA60 breadth: 35% - 70%
stock 20-day return > 0
stock 5-day return > 0
risk_pct: 3% - 6%
sweep pierce >= 0.3 ATR
zone width < 3%
```

Observed metrics:

| Metric | Value |
|---|---:|
| trades | 51 |
| WR | 92.16% |
| avg_pnl | +3.9496% |
| SL rate | 7.84% |
| TP rate | 92.16% |
| semantic failures | 0 |
| T+1 failures | 0 |
| field failures | 0 |

Year split:

| Year | n | WR | avg_pnl |
|---|---:|---:|---:|
| 2023 | 3 | 66.67% | +0.7074% |
| 2024 | 2 | 50.00% | +0.1548% |
| 2025 | 46 | 95.65% | +4.3260% |

Decision: `NO_PRODUCTION_YET_WR_OK_BUT_N_LT_100_AND_2023_2024_2026_SPARSE`.

## Additional V70 Fast-Repair Closure Lesson (same class)

When the user says “开始执行全量修复，完成后再次全量回测，逐笔检查分析，复盘，尤其是信号组合…”, do not stop after launching a background matrix job or reporting that a probe is running. Complete the loop in the same task:

1. Finish/recover the matrix or run a faster full-market audit if the full detector rebuild is too slow.
2. Apply signal-combo similarity de-duplication per symbol before judging whether repeated setups are inflating results.
3. Re-run full-market metrics, then audit semantic order, T+1, required frontend fields, and loser samples.
4. Explicitly decide production/frontend sync: **only sync if the target gate is met**.

Concrete fast-repair result from the follow-up full-market loop:

| Scope | n | WR | avg_pnl | SL rate | Decision |
|---|---:|---:|---:|---:|---|
| V68 raw | 5,546 | 58.17% | +1.0758% | 41.65% | baseline too low |
| Similarity de-duplicated | 5,306 | 58.61% | +1.1273% | 41.22% | repeated combos are not the main problem |
| Best production-size pre-entry gate subset | 157 | 67.52% | +1.5779% | 31.85% | still far below 90%; no promotion |
| Highest 90%+ subsets | 21–25 | 90–92% | +2.7% to +5.0% | 8–10% | too small; research only |

Best production-size gates observed in that loop:

```json
{
  "delay": [1, 3],
  "risk": [3, 6],
  "liq_confirm_gap": [1, 4],
  "pierce_lo": 0.3,
  "zone_width_hi": 3
}
```

This improved SL rate but did **not** solve the 90% requirement. The durable conclusion is stronger than “needs more filtering”: if FVG L→D zone-limit/reclaim variants top out around 58–78% at scale and only reach 90% in tiny subsets, the next repair must change/extend the signal source (e.g. 60m/15m reaction confirmation, second liquidity confirmation, BSL attraction validation, or true post-touch reclaim), not continue SL/TP or narrow historical filters.

## Key Lesson

When `ZONE_DEAD` dominates SLs (V68: 97% of SL_HIT), the engine is not suffering from stop placement noise; it is accepting invalid/low-quality demand zones. A 90% WR target requires a new confirmation layer or regime/quality gates. A 90%+ subset is not production-valid unless it has enough trades (prefer n>=100–200), zero audit failures, and acceptable year/regime robustness. Similarity de-duplication is a required diagnostic but, by itself, may only move WR marginally.

## Files from the reference sessions

- `/root/.hermes/scripts/v25/v68_sl_autopsy.py`
- `/root/.hermes/scripts/v25/v69_matrix_audit.py`
- `/root/.hermes/scripts/v25/v70_fast_signal_gate_search.py`
- `/root/.hermes/scripts/v25/v70_precision_candidate.py`
- `/root/.hermes/scripts/v25/v70_fast_repair_from_v68.py` — fast full-market repair loop from verified V68 trades: similarity de-dup, pre-entry gate beam search, best-candidate loser review, no-promotion decision.
- `/root/.hermes/smc_opt_v68_strict_ld/v68_sl_autopsy.json`
- `/root/.hermes/smc_opt_v69_matrix/v69_matrix_report.json`
- `/root/.hermes/smc_opt_v70_precision/v70_precision_report.json`
- `/root/.hermes/smc_opt_v70_fast_repair/v70_fast_report.json`
- `/root/.hermes/smc_opt_v70_fast_repair/v70_fast_report.md`

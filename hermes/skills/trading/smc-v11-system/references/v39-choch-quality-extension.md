# V39 CHOCH Quality Extension (2026-05-23)

## Trigger
Use this reference when SMC trade count is too low and the user asks to diagnose which filters suppress trades or to increase trade count without sacrificing signal correctness, WR, SL rate, or RR.

## Durable lesson
Do not increase trade count by broadly enabling all CHOCH/BOS, BRK/LV/RB, or no-retrace entries. In V38/V39 full-market tests, the largest trade-count bottleneck was the MSS-only gate, but broad relaxation destroys quality. The safe path is a narrow ordinary-CHOCH quality subset.

## Full-funnel finding
V38 funnel diagnosis showed:

- Total structure events: 53,723
- Bullish structure events: 26,514
- MSS events: 3,956
- OB zone touch: 1,559
- OB zone confirmation: 357
- Final V38 trades: 12

Largest suppressors:

1. Ordinary CHOCH/BOS filtered by MSS-only gate: 22,558 events
2. Price never truly retraced to POI / zone invalidated first
3. Zone retrace without bullish confirmation
4. Candidate signal families BRK/LV/RB produced more trades but failed quality gates

## Unsafe expansions already tested
Full-signal candidate V38p produced 20 trades but failed quality:

- WR 65.0%
- SL rate 25.0%
- Avg PnL +0.74%

By signal family:

- BRK: 4 trades, WR 50.0%, SL 50.0%, Avg PnL -1.62%
- LV: 3 trades, WR 0.0%, SL 66.7%, Avg PnL -2.32%
- RB: 1 trade, WR 100.0%, sample too small

Therefore BRK/LV/RB should remain display/audit signals unless a future stricter quality rule is proven.

## V39 promoted rule
Ordinary CHOCH can be admitted only if all conditions hold:

1. Has EQL/EQH / liquidity-pool SSL sweep
2. Market state is RANGE
3. Zone width <= 1.0%
4. Confirmation occurs within 6 bars of CHOCH
5. Sweep-to-CHOCH gap <= 20 bars
6. CHOCH candle body/range >= 0.20
7. Still requires true zone touch/retrace
8. Still requires bullish zone confirmation

Still forbidden:

- Plain BOS
- CHOCH without liquidity-pool sweep
- CHOCH in TREND_UP / TRANSITION / TREND_DOWN / HIGH_VOL
- Zone width > 1.0%
- Entry before actual POI retrace
- Entry without zone confirmation

## V39 result
V39 promoted over V38 because it improved both quantity and quality:

| Version | Trades | WR | SL rate | Avg PnL | Total PnL |
|---|---:|---:|---:|---:|---:|
| V38 | 12 | 83.3% | 8.3% | +2.15% | +25.83% |
| V39 | 13 | 84.6% | 7.7% | +2.60% | +33.79% |

V39 decomposition:

- MSS: 12 trades, WR 83.3%, SL 8.3%, Avg PnL +2.15%
- ordinary CHOCH subset: 1 trade, WR 100%, SL 0%, Avg PnL +7.96%
- OB: 7 trades, WR 85.7%, Avg PnL +3.34%
- FVG: 6 trades, WR 83.3%, Avg PnL +1.74%

## Files from session

- Engine: `/root/.hermes/scripts/v25/v39_final_engine.py`
- Candidate engine: `/root/.hermes/scripts/v25/v39_choch_engine.py`
- Grid collector: `/root/.hermes/scripts/v25/v39_choch_collect_grid.py`
- Metrics: `/root/.hermes/smc_opt_v39/v39_metrics.json`
- Report: `/root/.hermes/smc_opt_v39/v39_choch_extension_report.json`
- Grid results: `/root/.hermes/smc_opt_v39p/v39_choch_grid_fast.json`

## Workflow rule for future sessions
When trade count is too low:

1. Run a funnel diagnosis by signal/event/state/retrace/confirmation layer.
2. Rank filters by absolute suppressions, not intuition.
3. Test broad candidate expansion first to prove what fails.
4. Promote only sub-rules that improve or preserve WR, SL rate, PF/RR, and trade count.
5. Sync front-end active version and verify `/api/summary` and `/api/kline?ver=<version>` after promotion.

# V55 lessons: pre-trade gates, adaptive TP, and structure signal sync

## Trigger
Use this reference when SMC work touches:
- Backtest/live page transaction logs.
- BOS/CHOCH/MSS missing from K-line charts.
- TP1/TP2 design, structure-break exits, or breakout validation.
- Any post-hoc quality filter that would be unsafe in live trading.

## Durable lessons

### 1. Post-hoc filtering is research-only; live systems need pre-trade gates
A sequence like:

1. generate complete trades
2. calculate SL/TP/exits
3. get true backtest outcomes
4. filter/reject bad outcomes afterwards

is acceptable for diagnostics but not for production/live selection. The same intent must be moved before entry as a pre-trade gate. Otherwise a live system would enter trades that the report later hides.

Pre-trade gates should block or down-rank candidates using only information available before entry, for example:
- structural SL is too far and would be artificially tightened by max-risk cap;
- entry is too far above raw zone (chasing);
- entry is below/through raw zone (zone invalidated);
- risk_pct exceeds allowed range;
- confirmation is weak or not executable;
- liquidity void / wide zone makes the entry imprecise.

Keep rejected candidates in a separate file/table (`REJECTED_PRETRADE_GATE`) so auditability is preserved without pretending they were tradable.

### 2. BOS/CHOCH/MSS may exist in snapshot but disappear due to frontend family mapping
When K-line charts show almost no BOS/CHOCH/MSS, do not assume signal generation failed. First inspect the API payload/signals list.

Common bug: signal snapshot stores these events with `family = structure`, while the frontend layer/filter expects separate `bos`, `choch`, and `mss` families. Fix by deriving family from type:

```python
if family == 'structure':
    if type.startswith('BOS_'):
        family = 'bos'
    elif type.startswith('CHOCH_'):
        family = 'choch'
    elif type.startswith('MSS_'):
        family = 'mss'
```

Also preserve provenance fields for chart/debugging:
- `pivot_idx`, `pivot_date`, `pivot_price`, `pivot_label`
- `line_start_idx`, `line_end_idx`, `line_start_price`, `line_end_price`
- `source_level`, `break_price`, `sweep_date`
- `pine_rule`, `line_semantics`

Verification should query `/api/kline_full?...` and count families/types before claiming the chart is fixed.

### 3. TP1/TP2 should not be fixed across all market regimes
Fixed TP1/TP2 (for example 1.5R/3.2R) is structurally weak because it sells too early in strong trends and waits too long in weak/range states. Use a trend-context TP plan before entry, while keeping the main position on structure-runner exit.

Example regime-based plan:
- `STRONG_TREND`: TP1 2.0R, TP2 4.5R
- `TREND`: TP1 1.8R, TP2 3.8R
- `RANGE/WEAK`: TP1 1.3R, TP2 2.4R

Trend context can use pre-entry features such as MA10/MA20 relation, MA20 slope, close vs MA20, distance from recent high, and ATR-normalized range. Store the selected plan in each trade/pick so frontend logs show the design actually used.

### 4. Define structure-break exit precisely
Do not write “structure break exit” without specifying the trigger. A robust definition should separate:
- intrabar pierce / wick touch;
- pending break;
- reclaim;
- confirmed close break;
- strong-trend runner exception;
- structural timeout.

Preferred rule:
- intrabar break that reclaims by close does not exit;
- close below dynamic structure stop creates pending/confirmed break;
- if subsequent reclaim occurs, cancel the exit;
- only confirmed structure break exits the runner;
- strong-trend runner may ignore ordinary structure noise until structural timeout.

### 5. True/false breakout validation belongs in signal quality
Breakout cannot be validated by high/low crossing alone. Use a score/gate combining:
- close crossover/crossunder of a confirmed pivot/current level;
- displacement/body quality;
- volume or range expansion when available;
- no immediate reclaim in the next 1–3 bars;
- no immediate zone invalidation;
- retest holds the raw zone;
- context/trend supports continuation.

False breakout patterns include wick-only breaks, sweep-and-reclaim, pending break followed by reclaim, break then rapid return into range/zone, and structure break without displacement.

### 6. Backtest/live pages must expose full execution logs
For SMC systems, aggregate WR/RR is insufficient. Backtest/live logs should include at least:
- symbol and stock name;
- trigger date, entry date, exit date;
- signal type and signal price;
- current/exit price;
- signal sequence/provenance;
- score/grade;
- SL, TP1, TP2;
- exit reason;
- partial-exit/leg logs;
- design plan used for TP/trailing/structure break.

This lets the user audit signal correctness, entry correctness, and exit correctness in one screen.

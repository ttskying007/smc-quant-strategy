# V15 Dual-Engine Architecture

## Motivation
User wanted V12's proven high-WR signals merged into V13. V15 implements dual-engine parallel backtesting and stock picking.

## Engine Design
Both engines share the same OB_Bull signal source (detect_all_signals_v22), differ only in entry conditions:

### V13 Engine (Zone Retrace Entry)
- Trigger: OB_Bull -> Demand Zone -> unbreached -> price retrace to zone bottom <=2% -> enter
- Age: <=120 bars
- SL: cost_line * (1 - ATR% * 1.2)
- TP: entry + 2*ATR
- Result: 621 trades, 94.5% WR, +8.48% avg

### V12 Engine (Retrace + Trend Confirm)
- Trigger: OB_Bull -> trend confirmed (close>MA20 + not trending down + dist from 60d high <=20%) -> unbreached -> retrace to zone bottom <=3% -> enter
- Age: <=80 bars (stricter)
- SL/TP: same as V13
- Result: pending (was in progress at session end)

## Key Lesson: V12 Cannot Use Immediate Entry
V12 initially used "OB bar next day immediate entry + trend filter" -> 5955 trades, 55.2% WR disaster.
Root cause: immediate entry doesn't wait for price to retrace to zone cost line -> SL distance too large -> 39.7% stop rate.
Fix: V12 now uses same retrace entry logic as V13 + extra trend confirmation.

## Scanner Tightening
retrace_pct <= 3% was the key filter to go from 2284 to 211 picks.

# SMC AI Analysis Engine — Automated Signal Quality Assessment

## Overview

`ai_analysis_engine.py` performs multi-dimensional analysis of SMC backtest results:
1. Signal quality per type (WR, avgPnL, W/L ratio, TP rate)
2. Entry/exit timing (perfect vs early vs late)
3. SMC context impact (LIQ Sweep, CHOCH, swing point, FVG nearby)
4. OB_Bull deep dive (daily vs 60min entry comparison)
5. Automated recommendations based on findings

## Key Findings (from V9 17,008 trades)

### SMC Context WR Gradient
| Contexts | WR | Interpretation |
|----------|-----|---------------|
| ctx_0 (isolated) | 42.3% | Unusable — skip these signals |
| ctx_1 | 64.3% | Marginal |
| ctx_2 | 79.4% | Acceptable |
| ctx_3 | 87.3% | Strong |
| ctx_4 | 92.0% | Excellent — 2x isolated |

### OB_Bull Entry Source
| Source | WR | avgPnL | 
|--------|-----|--------|
| Daily direct | 99.4% | +9.69% |
| 60min precise | 59.7% | +6.02% |

**Conclusion**: 60min "precise" entry REDUCES WR for OB_Bull. Daily signals are more reliable. 60min should only be used as supplementary confirmation.

## Cron Job
- ID: efb8988922b7
- Schedule: Daily 9:00 AM
- Actions: Run ai_analysis_engine.py → Run v10_smart_money_engine.py → Sync frontend → Report

# V19 Closed-Loop Self-Iteration

## Architecture

```
V19 Engine ──→ 全量4905回测 ──→ 5维实证复盘
    ↑                                  ↓
    │                          聚合改进建议
    │                                  ↓
    │                          影响>20%? ──→ 自动修改params_override
    │                                  ↓
    └──────── 重跑全量验证 ←───────────┘
                     ↓
              评分对比(prev vs current)
                     ↓
          improved? ──→ keep fix, continue
                     ↓
          stagnant? ──→ stop (delta < 0.1)
```

## Key Files

| File | Purpose |
|------|---------|
| `/tmp/v19_engine.py` | Main engine: backtest + autopsy + iteration loop |
| `smc_opt_v19/v19_params_override.json` | Parameter overrides applied between iterations |
| `smc_opt_v19/v19_i{N}.json` | Per-iteration trade data |
| `smc_opt_v19/v19_iteration_history.json` | Score trajectory across iterations |

## Auto-apply Rules

Only improvements affecting >20% of trades are auto-applied:

| Fix Type | Parameter | Multiplier |
|----------|-----------|------------|
| TP too low | tp_last_mult | ×1.2 |
| SL too tight | sl_mult | ×1.15 |
| TP too high | tp_last_mult | ×0.85 |

## Iteration Stop Conditions

1. Max 3 iterations reached
2. No improvement >20% impact found
3. Score delta < 0.1 (stagnation)
4. All dimensions > 4.0 (no critical weakness)

## Cron Integration

Job `ee71ba342c94`: daily 09:00
- Runs V19 closed-loop
- Compares scores across iterations
- Auto-rollback if score degrades >0.3
- Updates frontend picks
- Restarts smc_unified.py

# V18 闭环自迭代架构

## 迭代流程

```
┌──────────────────────────────────────────────┐
│  Iter#1: 初始回测 (4905只全量)                │
│  ├─ backtest_stock_v18() × 4905              │
│  ├─ TradeAutopsy.run() × 295笔               │
│  └─ aggregate_improvements() → Top改进       │
├──────────────────────────────────────────────┤
│  自动应用修复 → params_override.json          │
│  ↓                                           │
│  Iter#2: 参数覆盖回测                          │
│  ├─ backtest_stock_v18(params_override={...}) │
│  ├─ TradeAutopsy.run() × 295笔               │
│  ├─ 对比Iter#1评分 → 提升/停滞/下降?          │
│  └─ 评分停滞(Δ<0.1) → 停止                   │
│  ↓                                           │
│  Iter#3: 继续?                                │
└──────────────────────────────────────────────┘
```

## 参数覆盖机制

`v18_params_override.json` 支持:

| 参数 | 含义 | 示例 |
|------|------|------|
| tp_last_mult | TP最后一层倍数 | 1.2 (扩大20%) |
| sl_mult | SL乘数 | 1.15 (放宽15%) |

```python
# 引擎中应用
if params_override:
    if 'tp_last_mult' in params_override:
        regime_params['tp_tiers'][-1] *= params_override['tp_last_mult']
    if 'sl_mult' in params_override:
        regime_params['sl_initial_pct'] *= params_override['sl_mult']
```

## 停止条件

1. 达到MAX_ITERATIONS(3轮)
2. 无可自动应用的改进(<20%影响面)
3. 评分提升<0.1(停滞)

## 运行

```bash
python3 /tmp/v18_engine.py
# 或通过cron ee71ba342c94 (每日09:00)
```

## 输出

- `v18_autopsy_i{N}.json` — 每轮交易+复盘
- `v18_improvements_i{N}.json` — 每轮聚合改进
- `v18_iteration_history.json` — 评分轨迹
- `v18_params_override.json` — 当前参数覆盖
- `v18_autopsy.json` / `v18_improvements.json` — 最终数据

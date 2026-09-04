# V38 — 多自适应共振交易系统 (2026-05-09)

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│ V38 回测引擎 (rolling_backtest_v38.py)                      │
├─────────────────────────────────────────────────────────────┤
│ 信号源: detect_all_signals_v11 → FVG/OB/Sweep/CHOCH/BB...  │
│ 结构树: StructureTree(micro/meso/macro 3层)                 │
│ 阶段: WyckoffPhase(accumulation/markup/distribution/...)     │
│ 入场: evaluate_v38_entry → 多入口 + 双向                     │
│ 出场: calc_v38_trailing → 结构感知 trailing                   │
└─────────────────────────────────────────────────────────────┘
```

## 组件文件

| 文件 | 行数 | 功能 |
|------|------|------|
| `/root/.hermes/scripts/v11/structure_tree_v38.py` | ~250 | 3层结构树 |
| `/root/.hermes/scripts/v11/wyckoff_phases_v38.py` | ~280 | Wyckoff 4阶段 |
| `/root/.hermes/scripts/v11/rolling_backtest_v38.py` | ~280 | 综合回测引擎 |
| `/root/.hermes/scripts/v11/run_v38_full.py` | ~150 | 全量4800扫描 |

## 结构树算法 (StructureTree)

3层摇摆点检测: micro(3,2) / meso(8,5) / macro(20,10) 窗口

```
StructureTree.__init__(ohlcv):
  每层:
    highs, lows = detect_swings(ohlcv, window, min_bars)
    trend = HH/HL序列分析 (up/down/neutral)
    levels = nearest support/resistance

关键方法:
  get_sl_level(entry_idx, entry_price):
    找entry前最近摆动低点 (macro→meso→micro优先级)
    返回 (sl_price, 'structure_macro', sl_pct)

  get_tp_level(entry_idx, entry_price, direction):
    bull: 找entry后摆动高点 (阻力位)
    bear: 找entry后摆动低点 (支撑位)
    返回 (tp_price, 'swing_high_macro', tp_pct, tp_idx)

  is_consolidation(lookback=20): 波动率<8%判定
```

### 陷阱

**STRUCTURE TP方向 (CRITICAL)**: `get_tp_level()` 最初只返回摆动高点(适用于做多), 做空时需要返回摆动低点。修复后接受 `direction='bull'|'bear'` 参数。

## Wyckoff阶段检测 (detect_wyckoff_phases)

4阶段评分系统, 每个独立评分 0-1.0:

| 阶段 | 信号 | 阈值 | 亚类型 |
|------|------|------|--------|
| accumulation | 窄幅+缩量+回测+Spring | >=0.45 | spring / base_building |
| markup | HH/HL+放量+突破 | >=0.45 | breakout / trending |
| distribution | 阻力区+量高价弱+Upthrust | >=0.40 | upthrust / top_building |
| reaccumulation | 前期上升+中位盘整+缩量 | >=0.40 | middleground / base_building |

阶段自适应参数映射:
```python
PHASE_ADAPTIVE_PARAMS = {
    'accumulation': { 'sl_mult': 0.6, 'tp_mult': 2.0, 'min_score': 0.50 },
    'markup':        { 'sl_mult': 0.8, 'tp_mult': 2.5, 'min_score': 0.60 },
    'distribution':  { 'sl_mult': 0.5, 'tp_mult': 1.5, 'min_score': 0.70, 'bear_bias': True },
    'reaccumulation':{ 'sl_mult': 0.7, 'tp_mult': 2.0, 'min_score': 0.55 },
    'unknown':       { 'sl_mult': 0.7, 'tp_mult': 2.0, 'min_score': 0.60 },
}
```

### 实测效果

Wyckoff阶段对WR影响极小:
- accumulation: WR=93.6%
- unknown: WR=93.3%
- 差异仅0.3pp — 可以忽略

## 做空交易 (Bear)

1. 信号类型过滤: FVG_Bear / OB_Bear (与Bull共用检测引擎)
2. PnL计算: `pnl = (exit - entry) / entry * 100`, 若方向bear则 `pnl = -pnl`
3. 趋势过滤: 做空时短趋势不能是 'up'
4. 周线过滤: 周线趋势不能是 'up'
5. 三层趋势: 不能有2个或以上up趋势

### 做空陷阱

**BUG — Bear PnL双次取反 (V38.0)**: `${pnl} = (exit - entry) / entry * 100` 计算的是做多视角的PnL. 做空时取反一次. 但 `calc_v38_trailing` 中 `return j, tp_price, True` 返回硬编码 `True` (won). 这是错误的 — 应该用 `tp_price < entry_price` 判断是否真的盈利.

**BUG — 结构TP方向 (V38.0)**: `get_tp_level()` 只找摆动高点(阻力位), 做空的TP应该是摆动低点(支撑位). 修复: `get_tp_level(entry_idx, entry_price, direction)`.

## 入场逻辑 (evaluate_v38_entry)

只接受 Bull/Bear 分别评估, 信号类型过滤:

| 信号类型 | Bull | Bear | 质量要求 |
|----------|------|------|----------|
| FVG | FVG_Bull in type | FVG_Bear in type | confidence>=0.55 |
| OB | OB_Bull in type | OB_Bear in type | confidence>=0.50 |
| BreakerBlock | BB_Bull + has_fvg_overlap | — | metadata检查 |

### 过滤链

1. 成交量: 信号bar成交量 > 30日均值 * 0.6
2. 短趋势: 做空不能 'up', 做多不能 'down'
3. 周线趋势: 同上
4. 三层趋势 (8/20/40): 不能有2+反向趋势
5. 序列: 需要SCOUT及以上
6. 共振: 分数 >= phase_params['min_score'] (默认0.60)
7. make_entry_decision_v11: action必须='enter'

## SL计算 (calc_v38_sl)

3层优先级:
1. 结构树SL (macro→meso→micro)
2. 信号结构SL (FVG lower/upper, OB lower/upper)  
3. ATR自适应SL (atr*0.3*phase_factor, 最低0.15%, 最高1.5%)

## TP计算 (calc_v38_tp)

3层优先级:
1. 结构树TP (micro→meso→macro)
2. 前方CHOCH break_level (Bull: 阻力, Bear: 支撑)
3. 无结构TP → trailing

## Trailing (calc_v38_trailing)

- 有结构TP: 接近TP 95%时收紧, 到达止盈
- 无结构TP:
  - gain>4%: 锁2%回撤
  - gain>2%: 锁1%回撤
  - gain>1%: 保本+0.5%
  - gain>0.5%: 保本+0.2%
- 做空版本: 追踪最低价, 反向trailing

## 全量4800结果

文件: `/root/.hermes/smc_opt_v38/backtest_v38_full.json`

```
Total: 67,002 trades, 4282/4800 stocks tradable
WR=92.7%  RR=3.10x  PF=44  avgP&L=+2.47%
Bull: 43,459 trades  WR=92.0%  RR=3.51x
Bear: 23,543 trades  WR=94.0%  RR=2.33x
FVG:  37,335 trades  WR=89.0%  RR=2.71x
OB:   29,667 trades  WR=97.4%  RR=3.59x
```

### WR分布
| 区间 | 股票数 | 占比 |
|------|--------|------|
| 100% | 1,514 | 35.4% |
| 90-99% | 1,554 | 36.3% |
| 80-89% | 989 | 23.1% |
| 70-79% | 166 | 3.9% |
| 60-69% | 45 | 1.1% |
| 50-59% | 14 | 0.3% |

## 已知问题

1. Wyckoff阶段检测效果有限 — 与随机状态WR相差仅0.3%
2. BreakerBlock+FVG重叠(一击必中)信号太罕见, 全量4800中0次触发
3. 做空RR (2.33x) 显著低于做多 (3.51x)
4. 566/4282只股票RR=1x — SL和Entry Price太接近
5. 全量扫描Python输出缓冲 — 需 `PYTHONUNBUFFERED=1` 或 `-u` 标志
6. V38后端不支持ETF/指数 — Hubble API 401限制了测试范围

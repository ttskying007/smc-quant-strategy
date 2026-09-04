# V46.1 SMC 信号正确性与分层质量修复笔记

## 适用场景
当 SMC 系统出现以下问题时使用：
- OB/FVG/BOS/CHOCH/MSS 信号看起来和 Pine/LuxAlgo 不一致。
- 回测指标不错但用户怀疑信号机制不正确。
- 前端 K 线标识、选股、回测、watchlist 数据不同步。
- 盈亏比低，但要求不降低胜率。

## 本轮稳定做法

### 1. 先修语义，不先调 WR/RR
用户明确要求信号正确性优先。处理顺序：
1. 对齐 Pine/LuxAlgo 参数和信号语义。
2. 做全量结构审计，确认 bad_events=0。
3. 再用分层过滤提升质量。
4. 最后同步前端并验证 `/api/reload`、`/api/picks`、`/monitor`、`/api/kline_full`。

### 2. MSS 必须拆成图表预警与交易确认
- `is_mss`：图表层 MSS early-warning，CHOCH + recent sweep 即可。
- `is_mss_confirmed`：交易层 reversal 触发，必须更严格。

修复点：
- `v34c_next_open.py` 中 trading gate 应使用 `is_mss_confirmed`。
- V46.1 实际链路走 `v45_1_recall_repair.py -> v41.backtest_v34_setups()`，所以也必须同步改 `v45_1_recall_repair.py`。

避免错误：不要把图表 early-warning MSS 直接作为交易 reversal 入场条件。

### 3. Pine/LuxAlgo 结构参数
从用户截图 OCR 得到的关键参数：
- `Swing Length = 5`
- `OB Swing Detection Length = 7`
- `OB Lookback = 10`
- `OB Displacement Multiplier = 1.5`
- `EQH/EQL Pivot Length = 4`
- `EQH/EQL Threshold = 0.1`
- `Minimum Strength Filter = 3`

已验证的重要修复：
- `smc_core_luxalgo_v34.py` 默认 `swing_len=5`。
- `bootstrap_cutoff` 从 `size * 2` 改为 `size`，避免额外吞掉已确认 pivot。
- `smc_core_pine_like.py` 保留 `ob_backscan=10`，`ob_displacement_mult=1.5`，`eq_len=4`。

### 4. FVG 边界
FVG raw boundary 保持 Pine 三蜡烛定义：
- Bullish FVG: `current low > high[2]`
- raw zone: `[high[2], current low]`

不要把 raw zone 改成 midpoint/display/execution zone。交易可用子区可以在执行层另算，但结构边界必须保留。

### 5. 三个主质量桶的处理
当目标是在不降低 WR 的前提下提高平均盈亏比，优先清理：

#### OB visual zone
硬过滤：
- `OB_NOT_VISUAL_SMC2026_ZONE`
- 或 `visual_ob_overlap < 0.35`

#### FVG executable boundary
硬过滤：
- `FVG_NOT_PINE_PARAM_OR_BOUNDARY_SHIFT`

不要硬杀所有 `FVG_TOO_WIDE`。本轮验证发现部分宽 FVG 仍有较好收益；该桶更适合作为降级/观察项。

#### Liquidity target
硬过滤：
- `liquidity_target_pct < 8`

这是低 RR 和低平均 PnL 的主因之一。

### 6. C 层过滤
当 C 层拖低胜率/SL/平均 PnL 时，直接剔除 C 层：
- 添加 `L3_FAIL_C_LAYER_LOW_RR_FILTER`
- `layer='REJECT'`

本轮效果：
- kept trades 从 391 降到 348。
- WR 从 84.7% 升到 85.6%。
- SL rate 从 14.8% 降到 14.1%。
- avg pnl 从 7.01 升到 7.17。

### 7. 验证清单
每次修复后必须做：
1. Python syntax check。
2. 全量结构审计：`v46_1_structure_audit.py`。
3. 全量/复用 base 回测：`v46_1_layered_3y.py --reuse-base` 或必要时 `--rebuild-base`。
4. 检查 report：trade 数、WR、SL rate、avg pnl、weighted metrics、issue buckets。
5. 检查问题桶是否仍进入 kept trades。
6. 重启 `smc_unified.py`。
7. 验证：
   - `/api/reload`
   - `/api/picks`
   - `/monitor`
   - `/api/kline_full?symbol=...&tf=daily&ver=V46_1`
8. 确认 K线 family 中有 `bos/choch/mss/ob/fvg/sweep`。

### 8. 前端同步坑
`smc_unified.py` K线标签映射必须包含：
- `BOS_Bull -> BOS`
- `BOS_Bear -> BOS`
- `MSS_Bull -> MSS`
- `MSS_Bear -> MSS`
- `FVG_Bull -> FVG`
- `FVG_Bear -> FVG`
- `CHOCH_Bull/Bear -> CH`

否则后端有信号但图上不显示完整。

### 9. 用户验收口径
对 Lei 交付时不要只报聚合指标。必须明确：
- 哪些机制已修。
- 哪些问题桶已不再进入 kept trades。
- 全量结构审计是否 bad_events=0。
- 前端同步是否完成。
- K线图是否显示一致。
- 是否还存在剩余问题桶，以及为什么没有硬杀。

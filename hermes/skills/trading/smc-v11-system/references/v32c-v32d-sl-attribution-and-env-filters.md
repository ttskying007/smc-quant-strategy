# V32C→V32D 止损归因方法论与环境过滤模式（2026-05-22）

## 触发场景

用户发现止损触发较多，要求全面排查是信号问题、入场点问题、SMC信号定义问题、组合方式问题还是未到入场点位。

## V32C→V32D MFE归因方法论

传统SL排查只分SL/TP/TIMEOUT三类，无法区分止损的**因果机制**。V32C引入基于MFE（Maximum Favorable Excursion in R-units）的六类归因：

| 归因 | 识别标准 | 机制 |
|------|----------|------|
| signal_false_positive | MFE < 0.35R | 结构信号位置正确但买力未兑现 |
| followthrough_fail | MFE 0.42-1.0R | 有涨幅但最终回撤触SL |
| weak_rejection | reject_strength < 0.45 或 bodypos < 0.55 | confirm candle质量不够 |
| gap_risk | exit_reason含GAP | A股隔夜跳空穿SL |
| high_vol_context | market_state=HIGH_VOL | 高波动环境做多不利 |
| oversized_zone | zone_width > 6% | FVG/OB过大导致SL偏宽 |

### 计算方法

```python
# MFE: entry后最大有利偏移 / risk
seg = klines[entry_idx+1:exit_idx+1]
max_hi = max(float(b['h']) for b in seg)
mfe = (max_hi - entry) / risk

# reject_strength: confirm candle的下影线占比
cb = klines[conf_idx]
rng = max(hi - lo, 1e-9)
reject_strength = (min(op, cl) - lo) / rng

# zone_width: PD array宽度占entry百分比
zone_width = (zone_high - zone_low) / entry * 100
```

### 归因优先级（从最明确到最模糊）

1. GAP → gap_risk（明确：A股结构性风险）
2. HIGH_VOL → high_vol_context（明确：环境不利）
3. zone_width > 6 → oversized_zone（明确：SL偏宽）
4. reject < 0.45 → weak_rejection（明确：确认质量差）
5. MFE < 0.35 → signal_false_positive（明确：买力不足）
6. MFE ≥ 1.0 → stop_after_profit（trail正常损耗）
7. else → followthrough_fail（涨了但回撤）

## 环境过滤模式（V32D）

当归因指向环境而非信号定义错误时，**先做逐机制全量矩阵验证，再决定是否启用过滤**。不要因为某一类SL归因看起来合理，就直接把它做成硬过滤。

### 原则

1. **不改信号定义** — OB/FVG/CHOCH/Sweep检测正确性已验证，环境过滤不影响核心逻辑
2. **不改SL/TP参数** — gap_risk是A股结构性风险，参数优化无效
3. **过滤必须提高整体期望** — 不只看“消除多少SL”，还必须看被误杀的盈利交易、total_pnl、avg_pnl、SL率
4. **逐机制验证优先于直觉过滤** — zone_width/reject_strength是审计字段，不天然适合作为硬阈值

### V32D全量过滤矩阵结果

| 过滤组合 | 交易数 | WR | avg_pnl | total_pnl | SL数 | SL率 | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|
| V32C基线 | 72 | 65.3% | 1.05% | 75.85% | 25 | 34.7% | 基线 |
| HIGH_VOL过滤 | 62 | 66.1% | 1.23% | 76.37% | 21 | 33.9% | **保留** |
| zone_width≤6 | 60 | 66.7% | 1.11% | 66.72% | 20 | 33.3% | 不保留，收益下降 |
| HIGH_VOL + zone≤6 | 51 | 66.7% | 1.16% | 59.41% | 17 | 33.3% | 不保留，收益下降 |
| reject_strength≥0.45 | 45 | 66.7% | 1.04% | 46.80% | 15 | 33.3% | 不保留，误杀高盈利 |
| 三项全开 | 34 | 61.8% | 0.83% | 28.30% | 13 | 38.2% | 失败 |

### 正式V32D只启用HIGH_VOL过滤

V32C中HIGH_VOL交易：n=10、WR=60%、SL_rate=40%、avg_pnl=-0.05%、total_pnl=-0.52%。过滤后：WR 65.3%→66.1%，avg_pnl 1.05%→1.23%，total_pnl 75.85%→76.37%，SL率 34.7%→33.9%。

```python
# 正式V32D：只拒绝HIGH_VOL；不改信号定义，不改SL/TP
if st['rr'] < MIN_RR: return None
if st['market_state'] in {'TREND_DOWN','TRANSITION','UNKNOWN','HIGH_VOL'}: return None
return st
```

### zone_width≤6 不启用

zone_width>6确实包含gap风险，但也包含高盈利交易（如300671.SZ +5.03%、688638.SH +10.46%、002940.SZ +10.41%）。硬过滤后total_pnl 75.85%→66.72%，收益下降9.13pp。

### reject_strength≥0.45 不启用

单根确认K的lower_wick比例不能作为硬过滤。reject_strength<0.45误杀强盈利交易（如688281.SH +16.52%、603712.SH +5.09%、301323.SZ +11.30%、688638.SH +10.46%）。硬过滤后total_pnl 75.85%→46.80%，收益下降29.05pp。

### 可审计性

后续仍可在setup/trade中存储 `reject_strength` 和 `zone_width_pct` 字段用于归因，但默认不要启用硬过滤。

## 入场点位修复（V32C limit retouch）

V32B根因：`entry_from_next_open` 把next bar open当成交价，即使open远高于zone也截断成交。
- 9/23笔SL(39%)的entry > zone_high（chase entry）

V32C修复：`entry_from_limit_retouch`
- 确认后只在实际回踩zone的bar成交
- next open高开脱离zone → setup标记为missed，不追价
- entry_above_zone从9笔→0笔

三种入场模式：
- `LIMIT_OPEN_IN_ZONE`: next open在zone内 → 直接成交
- `LIMIT_RETOUCH_ZONE_HIGH`: 等回踩zone后成交（zone_high限价）
- missed: 高开不回踩 → 不成交

## 关键教训

1. **MFE归因优于聚合统计** — SL率34.7%无法区分"买力不足"和"跳空穿SL"，MFE区分了6类机制
2. **环境过滤≠信号修改** — 当归因指向环境时，过滤环境而非调参数或改信号定义
3. **逐笔trace优于事后回归** — 后验filter sweep（8种组合）必须用全量矩阵验证；不要只看“消除SL数”，还要看误杀盈利交易和total_pnl
4. **A股gap_risk是结构性风险** — GAP_SL无法通过SL/TP参数规避；zone_width上限看似能减少gap，但全量验证会误杀高盈利交易，默认不启用
5. **reject_strength不是硬过滤条件** — 低lower_wick比例仍可能是强盈利setup；V32D验证中reject_strength≥0.45使total_pnl从75.85降到46.80
6. **环境过滤只保留正期望项** — V32D正式版只启用HIGH_VOL过滤，因为它同时提升WR/avg_pnl/total_pnl并降低SL率
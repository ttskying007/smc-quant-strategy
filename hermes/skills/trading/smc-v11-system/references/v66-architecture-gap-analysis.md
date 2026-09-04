# V66 架构差距分析：SMC 理论 vs V66 实现

## 核心发现

V66 不是真正的 SMC 系统，而是**带有 SMC 标签的突破交易系统**。信号层（V59 `smc_core_pine_like.py`）正确实现了 OB/FVG 的 Pine 对齐检测，但策略层（`daily_scan.py`）把这些信号当作突破信号而非 SMC 回撤确认信号使用。

**根本代码证据** (`/root/.hermes/scripts/v25/daily_scan.py:214-218`)：
```python
entry_idx = c.bar + 1              # 确认bar的下一根开盘进场
if entry_idx != latest_idx:        # 只交易最新bar
    continue
entry_price = klines[entry_idx].get('o')  # 开盘价入场
```

**结果**：137/137 笔交易 entry_idx == conf_idx+1，100% 无回撤等待。系统在 BOS/CHOCH 发生后的下一根开盘立即入场，从不等待价格回到 POI。

## 6 项架构缺失

| # | 缺失项 | V66 实际 | 真实 SMC 要求 | 数据证据 |
|---|--------|---------|--------------|---------|
| 1 | 回撤到 POI | entry_idx = conf_bar+1 | BOS/CHOCH → 价格回到 OB/FVG → 在 POI 确认 → 入场 | 137/137 无回撤 |
| 2 | 流动性抓取前序 | 不检查 sweep | Sweep(扫止损) → 确认机构意图 → 结构破位 | 0/137 有 sweep |
| 3 | 市场状态 | market_state=137/137="?" | 区分 TREND_CONT/REVERSAL/RANGE/FALSE_BREAK | 137 笔 "?" |
| 4 | 入场模式 | 全推断值 | 区分 retrace/immediate/reentry | 无真实计算 |
| 5 | SL 位置 | 45 笔 SL=zone_low | SL = zone_low - ATR_buffer | 8/12 SL 笔 SL=zone_low |
| 6 | 多信号合流 | 仅 5 种单信号组合 | OB+FVG+CHOCH 三重合流 | 0 笔三重合流 |

## V66 实际交易逻辑

```
找 OB/FVG zone → 等 BOS/CHOCH 确认 → entry_idx = c.bar + 1 (下一根开盘入场) → SL 在 zone_low
```

## 真实 SMC 应有的交易逻辑

```
抓流动性(扫止损 at EQH/EQL) → 结构破位(CHOCH/BOS 确认方向) → 价格回撤到 POI(OB/FVG 区域) → 
在 POI 出现确认 K 线(拒绝形态/Pinbar/MSS) → 入场 → SL 在 POI 下方
```

## 代码定位

| 缺陷 | 文件 | 行 | 代码 |
|------|------|-----|------|
| 无回撤 | `daily_scan.py` | 216 | `entry_idx = c.bar + 1` |
| 仅最新 bar | `daily_scan.py` | 217 | `if entry_idx != latest_idx: continue` |
| 开盘入场 | `daily_scan.py` | 218 | `entry_price = klines[entry_idx].get('o')` |
| 组合 = type+conf 通吃 | `daily_scan.py` | 212-215 | `for z in zones: for c in confirms:` — 不检查 sweep 前序 |
| SL 在 zone_low | `daily_scan.py` | compute_sltp() | `v25_sl_price = round(sl_price, 2)` — sl_price = zl |
| setup_family = type 映射 | `smc_daily_ops.py` | 95 | `CONTINUATION_SETUP if zone_type == OB_Bull else REENTRY_SETUP` |

## V59 引擎状态（信号层，正确）

- ✅ OB 检测：从结构破位反向扫，取最近反向 K 线（Pine 对齐）
- ✅ FVG 检测：三 K 严格 gap 规则
- ✅ 结构状态机：BOS/CHOCH/MSS 摆动点检测
- ✅ Sweep 检测：sweep_signals_stateful 正确实现（但未被策略层使用为前序事件）
- ❌ 没有回撤等待：daily_scan.py 策略层不检测 retrace_to_zone
- ❌ 没有 POI 确认：策略层不等待拒绝 K 线

## 修复方向（不要重构，仅作参考）

### P0：重建入场逻辑
- `entry_idx = c.bar + 1` → 改为等待价格回测到 zone
- 增加 retrace_to_zone 检查：结构破位后，等待 price 进入 zone_low ≤ price ≤ zone_high
- 增加 POI 确认：在 zone 内出现拒绝 K 线(hammer/pinbar/engulfing)
- retrace 完成后才允许入场

### P0：增加 sweep 前置
- 在信号链中增加 sweep 检查：BOS/CHOCH 前必须有 sweep
- sweep → structure break → retrace → confirm → entry

### P0：计算真实 market_state
- 使用状态机区分：TREND_CONTINUATION / TREND_REVERSAL / RANGE_BREAKOUT / FALSE_BREAK
- 入场逻辑根据 market_state 调整参数

### P1：SL 设计
- SL = zone_low - ATR_buffer（不是 zone_low 本身）
- 追踪减仓后 SL 上移到盈亏平衡

### P1：多时间框架
- 60 分/日线/周线对齐
- 日线趋势向上 → 只做多
- 周线趋势向上 → 加大仓位

## 补充：纠正对固定 R 倍数的误解

上一轮分析认为 V66 使用固定 R 倍数（3.83x）计算 PnL，**该结论错误**。

**验证**：STRUCT_CONFIRM_BREAK 腿的 PnL 基于真实 trailing stop 价格计算：
- 非趋势跟踪（95 笔）：平均退出 R=4.10R（对应 `after_2r_lock_r=4.0`）
- 趋势跟踪（42 笔）：平均退出 R=8.87R（stop 跟随趋势持续上移）
- 13.42% PnL 是 exit plan 参数的数学结果：5% TP1@1.5R + 5% TP2@3.2R + 90% STRUCT@4.0R → 加权 13.4225%

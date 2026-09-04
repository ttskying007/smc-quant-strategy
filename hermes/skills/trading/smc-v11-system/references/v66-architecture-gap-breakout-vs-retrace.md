# V66 架构差距：V59信号正确但策略层是突破系统而非SMC回撤系统 (2026-06-10)

## 核心发现

V59引擎 (smc_core_pine_like.py) 的信号检测层与 Pine Script 对齐，基本正确。
但 **策略层** (daily_scan.py) 把这些信号当作**突破交易系统**使用，不是 SMC 的 POI 回撤入场系统。

### 数据证据 (137笔V66交易)

| 检查项 | 结果 | SMC要求 |
|--------|------|---------|
| entry_idx vs conf_idx | 137/137 entry_idx == conf_idx+1 | 应等待价格回撤到POI |
| sweep前序 | 0/137 有sweep | 应有 liquidity sweep → structure break |
| market_state | 137/137 = "?" (未计算) | 需要趋势/反转/盘整状态机 |
| 入场位置 | 91笔(66%)在zone上方 | 应在zone内25-50%位置 |
| SL vs zone_low | 45笔SL=zone_low(无缓冲) | SL应在zone_low - ATR*0.5 |
| 信号组合 | 仅5种(OB/FVG + BOS/CHOCH/MSS) | 缺少三重合流和sweep+zone |

### 关键代码位置

```python
# daily_scan.py:216-218 — 无回撤等待
entry_idx = c.bar + 1              # 确认bar的下一根直接入场
if entry_idx != latest_idx:        # 只交易最新bar
    continue
entry_price = klines[entry_idx].get('o')  # 开盘价入场

# daily_scan.py:183-196 — 无market_state
def _pass_daily_gate(zone_type, conf_type, score, trend_ctx, body_ratio):
    if zone_type == 'OB_Bull' and conf_type in ('BOS_Bull', 'CHOCH_Bull'):
        return True, [], 'CONTINUATION_SETUP'
    # 不检查市场状态

# compute_sltp() (内联daily_scan.py) — SL在zone_low
v25_sl_price = raw_zone_low  # 无buffer
```

### 修复路径

**Phase 0 (止血)**:
- SL buffer: `v25_sl_price = raw_zone_low * 0.99` (至少1%缓冲)
- 禁止追高: `if entry_price > zone_high * 1.008: continue`

**Phase 1 (重建)**:
- 新建 `smc_retrace_entry.py`: 等待价格回撤到zone内+拒绝K线确认
- 新建 sweep 前序验证: structure break 前必须有 sweep 事件
- 新建 `smc_market_state.py`: 状态机 (TREND_UP/DOWN/RANGING/BREAKOUT)
- 多 timeframe 对齐 (周线趋势过滤)

### V67 验证: 全量回测显示真实 WR=41%

V67_STRICT 用 90551笔全量回测，WR=41.15%。
V66 的 WR=90% 来自 V64(269笔)→V65(143笔)→V66(137笔) 的过度过滤，不是信号质量高。

### V65/V66 本质是后置过滤

V65 = 基于V64损失结果做loss-review gate (47%过滤)
V66 = 在V65上加REENTRY风险覆盖 (5%过滤)
两者都不改变 `entry_idx = c.bar+1` 的核心缺陷。

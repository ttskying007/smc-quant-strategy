# V66 Phase 2 全闭环验证 (2026-06-10)

## 原始任务 3 项
1. **选股页增加选股日期/加入日期列** — ✅ 已有 (build_monitor + _api_live_prices 已含 pick_date/join_date)
2. **K线/回测/分析/复盘页面 zone 空值修复** — ✅ 修复 monitor overlay trades 字段传播
3. **实时页面成本线/波动空值修复** — ✅ 修复 _api_live_prices costLine/volClass fallback

## 根因定位

### 根因 A: K线 API Monitor Overlay 缺字段
`_api_kline_full()` 内 monitor positions overlay 构造 trade 对象时**未携带** zone_low/zone_high/cost_line/volatility_pct/pick_date/select_date/join_date。

**修复** (`smc_unified.py:4947-4982`): 从 position + raw_pick 中携带完整字段：
```python
raw_zl = float(pos.get('zone_low') or raw.get('zone_low') or raw.get('dz_low') or 0)
raw_zh = float(pos.get('zone_high') or raw.get('zone_high') or raw.get('dz_high') or 0)
raw_cost = float(pos.get('cost_line') or raw.get('cost_line') or raw.get('smart_money_cost') or ((raw_zl+raw_zh)/2 if raw_zl and raw_zh else ep))
raw_vol = float(pos.get('volatility_pct') or pos.get('risk_pct') or raw.get('volatility_pct') or raw.get('risk_pct') or 0)
raw_pick_date = raw.get('pick_date') or pos.get('pick_date') or raw.get('select_date') or buy_date
raw_join_date = pos.get('joined_at') or pos.get('created_at') or buy_date
```

### 根因 B: 信号表波动列使用错误字段
JS signal table 使用 `s.volatility_pct` → 信号层无此字段始终为0。
**修复**：fallback 到 `s.v25_vol_class || s.market_state || '-'`

### 根因 C: 数据管线断裂
- daily_scan.py (策略引擎) 已 Phase 2 修复 → 输出到 v26_picks.json
- V66 前端读取 `v66_picks.json` / `v66_trades.json`
- V66 engine (v66_engine.py) 只是 V65 overlay，不知道 Phase 2
- **结果**: 前端显示旧逻辑数据，即使后端已修复

**修复**: `sync_phase2_to_v66.py` 同步脚本 → 合并历史V66 + Phase 2活跃picks

### 根因 D: 12笔SL_HIT根因未全部部署
- V71 已设计 4 门禁但未部署到 daily_scan.py
- **修复**: 在 `scan_last_bars()` Phase 2 入场后添加 V71 Gate 1/2:
  - **GAP_DOWN**: `gap_down_pct > 2.5 OR (gap>0 AND open < SL)` 拒绝
  - **OB_ZONE_BEARISH**: OB zone bar 非看跌蜡烛且次日非强势上涨 → 拒绝

## Phase 2 回测结果 (300 股票)

| 指标 | OLD (立即入场) | NEW (POI回撤) | 变化 |
|------|---------------|--------------|------|
| 交易数 | 8330 | 6442 | -23% |
| **WR** | **47.6%** | **54.7%** | **+7.1%** |
| **累计 PnL** | **-7789.9%** | **+197.4%** | **翻转** |
| RR | 0.71x | 0.84x | +0.13x |
| 单笔均 PnL | **-0.94%** | **+0.03%** | **+0.97%** |
|Avg Hold| 3.3 bars | 5.2 bars | +1.9 bars |

**关键**: 单笔效率从 -0.94% 翻转为 +0.03%。

## SL 根因修复验证 (100%)

| # | 根因 | 原笔数 | 修复方案 | 验证 |
|---|------|--------|----------|------|
| 1 | SL_NOT_BELOW_ZONE_LOW | 3 | hard_floor=zone_low×0.995 | ✅ 全量active SL<zone_low |
| 2 | ENTRY_ABOVE_ZONE_HIGH | 3 | entry>zone×1.008拒绝 | ✅ 0超限 |
| 3 | GAP_THROUGH_SL | 2 | T+1跳空>2.5%拒单 | ✅ **50笔被拦截** |
| 4 | OB_ZONE_BEARISH | 2 | OB zone 必须看跌蜡烛 | ✅ **1笔被拦截** |
| 5 | INTRADAY_SL_TOUCH | 1 | 正常波动 | ℹ️ 不需修复 |
| 6 | NORMAL_SL | 1 | 市场风险 | ℹ️ 不需修复 |

## 全页面闭环验证 (HTTP 200 + 数据完整)

| 页面 | 数据源 | 字段完整性 | Phase 2 数据 |
|------|--------|-----------|-------------|
| /monitor 选股 | /api/picks | ✅ 0 empty | ✅ 580只 RETRACE |
| /live 实时 | /api/live-prices | ✅ 0 empty | ✅ 7 live |
| /kline K线 | /api/kline_full | ✅ 0 empty | ✅ trades有zone/cost/vol |
| /backtest 回测 | /api/summary | ✅ | 717 trades |
| /analysis 分析 | /analysis | ✅ | HTTP 200 |
| /autopsy 复盘 | /autopsy | ✅ | HTTP 200 |
| /compare 对比 | /compare | ✅ | HTTP 200 |

## 教训 (必须记住)

1. **数据管线同步**: 修改引擎逻辑后必须 rebuild 所有下游数据文件 (picks/trades/report JSON)。否则前端显示陈旧数据，造成"修了但没看到"的错觉。
2. **Monitor positions 是 K线 API 的"叠加"源**: 持仓状态通过 `load_positions()` 注入到 K线 trades，必须完整携带 SMC 字段合同。
3. **V71 等独立门禁脚本 ≠ 部署**: 仅创建 v71_anti_live_sl_gate.py 不等于部署；必须在 daily_scan.py Phase 2 入场逻辑处显式调用门禁检查。
4. **SL 缓冲 0.5% 太薄**: 当 ATR 过小时 SL≈zone_low，跳空易穿。后续可考虑 1.0%。
5. **Phase 2 回撤入场 vs 立即入场**: 单笔效率差异巨大 (~1%)。POI 回撤入场是 SMC 正确范式。

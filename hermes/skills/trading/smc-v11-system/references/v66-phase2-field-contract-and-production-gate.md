# V66 Phase2 修复与生产门禁复盘（字段合同 + SL 根因 + 回测决策）

## 触发场景

当用户反馈：
- 选股页缺“选股日期 / 加入日期”；
- 选股页引擎后 Zone 为空；
- 实时页成本线 / 波动为空；
- Phase2 POI 回撤策略实盘大量 SL；
- 任务重跑仍出错或只修了页面没修机制。

## 必须执行的顺序

1. **先写/运行字段与机制验收脚本**，不要只看页面表头。
2. **同时检查三层数据源**：
   - `smc_opt_v25/v26_picks.json`
   - `smc_opt_v66/v66_picks.json`
   - `/api/picks` 与 `/api/live-prices`
3. **修复字段合同后必须重启 8890 并浏览器验收 `/monitor` 和 `/live`**。
4. **若策略效果不好，不准直接上线**：继续全量回测分桶，找正收益生产 profile 后再生产同步。

## 关键代码级坑

### 1. SL hard-floor 方向

`daily_scan.py::compute_sltp()` 中：

- 错误：`max(sl_base, hard_floor_sl)` 会把 SL 固定贴在 `zone_low * 0.995` 附近，ATR buffer 失效。
- 正确：多头 SL 必须在结构下方，使用 `min(sl_base, hard_floor_sl)`。

同时保留最终保护：若 `sl_price >= dz_low`，继续压到 `dz_low * 0.995` 以下。

### 2. 入场价格必须大于 SL 且不得跌破 zone

生产 active 候选必须满足：

```text
entry_price > sl_price
entry_price >= zone_low
```

否则会出现“入场即在止损下方”的硬错误。

### 3. score 不可被 SLTP 小分覆盖

`compute_sltp()` 里不要返回 `score` 覆盖前面的信号质量分。改为：

```python
'sltp_score': ...
```

保留 `score / breakout_quality_score` 作为选股排序分。

### 4. FVG/OB 与回撤深度要用全量回测决定

V66 Phase2 初始修复后，全市场 replay 显示：

| Profile | n | WR | SL | avg_pnl | cum |
|---|---:|---:|---:|---:|---:|
| baseline | 74793 | 36.56% | 62.67% | -0.4252% | -31800.37% |
| fixed broad | 6739 | 37.07% | 62.90% | -0.1554% | -1047.17% |
| FVG only | 4900 | 38.59% | 61.39% | +0.0092% | +45.03% |
| FVG + risk<3.5 + retrace<40 | 1586 | 41.55% | 58.45% | +0.2465% | +390.93% |

结论： broad fixed 只修 bug 仍不可生产；生产应选择经全量验证转正的 profile。

## V66 Phase2 推荐生产门禁

```text
zone_type == FVG_Bull
sweep_tag == SWEEP_TO_STRUCTURE
market_state not in RANGE/HIGH_VOL/TREND_DOWN/UNDEFINED
retrace_depth_pct < 40
risk_pct < 3.5
entry_price >= zone_low
entry_price > SL
T+1 严格执行：当天选股只 NEXT_DAY_PENDING，不当日买入卖出
```

## 字段合同补齐点

### picks 层

生产候选需要补齐：

```text
pick_date / select_date / join_date
zone_type / zone_low / zone_high / dz_low / dz_high
cost_line / smart_money_cost / v25_cost_line
volatility_pct / risk_pct / v25_sl_pct / v25_vol_class
sl / tp1
```

### monitor positions 层

`smc_monitor_state.to_position()` 应保留：

```text
join_date = raw join_date 或 joined_at/created_at/pick_date
cost_line = smart_money_cost 或 zone中线 或 entry
vol_class = v25_vol_class / market_state / regime / RISK
```

历史 `positions.json` 可做一次性 backfill，但不要把历史脏样本当作新生产候选。

### API 层

`/api/picks` 和 `/api/live-prices` 必须同时验收，空值统计应为 0：

```text
pick_date / pickDate
join_date / joinDate
zone_type / zoneType 或 zone_low/zone_high
cost_line / costLine
volatility_pct / volClass
```

## 验收脚本模式

新增/维护一个 deterministic verification script，至少检查：

- 文件级 active picks 无字段空值；
- API 级字段空值为 0；
- `entry_price <= SL` 为 0；
- `entry_price < zone_low` 为 0；
- RANGE/HIGH_VOL/TREND_DOWN active 为 0；
- FVG 无 sweep active 为 0；
- 深回撤 active 为 0。

## 上线门槛

只有同时满足以下条件才可称“生产完成”：

1. py_compile 通过；
2. 全量 daily scan 通过；
3. V66 merge 完成；
4. 全市场 replay 证明 profile 非负且优于 broad fixed；
5. `/api/picks` 与 `/api/live-prices` 字段空值为 0；
6. 8890 已重启；
7. 浏览器打开 `/monitor` 和 `/live` 首屏单元格有真实值；
8. 今日有效候选已进入 `NEXT_DAY_PENDING`，遵守 T+1。

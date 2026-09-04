# V66 前端/实时监控/回测一致性修复教训

适用场景：用户反馈 SMC 前端页面出现 K线信号偏移、实时监控买卖生命周期不一致、选股页面与回测页面数量/策略感知不一致。

## 1. K线信号偏移排查顺序

不要先假设是 ECharts 渲染问题。先做数据链路核对：

1. 调 `/api/kline_full?symbol=...&tf=daily&ver=V66` 看 `highlight` 的 `bar`。
2. 用同一响应里的 `klines[bar].date` 反查标记日期。
3. 对比最新候选文件字段：
   - `zone_bar` / `zone_date`
   - `entry_idx` / `entry_date`
   - `confirm_date`
4. 如果最新候选来自 `v66_daily_candidates.json`，K线高亮必须优先按 `zone_bar` 与 `entry_idx` 定位；不要只识别旧字段 `zone_idx` / `conf_index`。
5. 高亮编号不能固定从 2 开始，要从已有 highlight 最大编号 + 1 继续，避免视觉重复造成“偏移”错觉。

## 2. 大信号快照不能整文件解析

`/root/.hermes/smc_opt_v50_signal/v50_signal_snapshot.json` 约 700MB。K线接口如果整文件 `json.loads()`，容易 OOM 或服务被 kill，表现为 K线加载失败、标记不稳定、前端误判偏移。

稳定做法：按 symbol 用 mmap 局部读取该 symbol 的数组，不要全量解析。

## 3. 实时监控必须以真实 OPEN 持仓为准

实时页不是“候选列表页”。实时监控源必须是：

```text
/root/.hermes/smc_monitor/positions.json
status == OPEN
```

生命周期规则：

| 事件 | 实时页行为 |
|---|---|
| BUY / 汇入 OPEN 持仓 | 加入实时监控 |
| SELL / CLOSED | 从实时监控移除 |
| 候选仍在 picks 但已 CLOSED | 不显示在实时监控 |
| 重复汇入同一 symbol + pick_date + zone_type | 阻止重复 OPEN |

如果实时页继续从 `get_active_picks()` 或 picks 文件直接渲染，会出现“卖出后仍显示”“未买入候选伪装实时持仓”“重复 OPEN”等问题。

## 4. 最新日选与历史回测要分层解释

V66 当前至少有两类输出：

| 输出 | 文件 | 含义 |
|---|---|---|
| 历史回测交易 | `v66_trades.json` | 已完成买卖闭环的交易 |
| 最新日选候选 | `v66_daily_candidates.json` | 当日/近期扫描候选，可能尚未卖出 |

当用户用窗口如 `20260501~20260601` 回测只看到 1 笔，但选股/实时有更多候选时，先检查是否是：

- `v66_trades.json` 窗口内确实只有已闭环交易 1 笔；
- `v66_daily_candidates.json` 窗口内另有实时候选，但还没有完整 exit，不应计入历史交易统计。

页面应明确显示“一致性诊断”：历史回测交易数与最新日选候选数分别是多少，避免让用户以为选股策略和回测策略完全同源。

## 5. 验收要覆盖 API + 浏览器

最小验收：

```text
/api/picks                         含最新日选候选
/api/live-prices                   只显示 OPEN 持仓，CLOSED 不显示
/api/kline_full?...&ver=V66        highlight bar/date 与候选字段一致
/backtest?start=...&end=...        显示窗口交易数 + 一致性诊断
浏览器 /live /kline /backtest       页面实际渲染正常
```

不要只报告聚合指标；必须给出字段级核对结果。
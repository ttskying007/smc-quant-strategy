# V103A 生产链路/active/前端一致性审计教训

适用场景：用户质疑“底层全量信号很多，但生产池/active/前端只剩极少数”，或要求判断是否未来函数、后验筛选、生产链路语义错误。

## 核心审计顺序

1. **先分层计数，不先解释**
   - 全量信号/交易数
   - 组合族数量（REVERSAL、BOS 等）
   - 生产池 raw/clean 数量
   - removed-by-gate 数量
   - active 文件数量
   - `/api/picks`、`/api/live-prices`、`/api/summary` 实际返回数量
   - 计算压缩倍数：full→production、full→active、full→frontend。

2. **生产池不是 active**
   - production pool 可以是历史回测高质量样本。
   - active/watchlist 必须来自最新全市场扫描或真实监控状态。
   - 如果 active 行已经有 `exit_reason`、`exit_date`、`net_pnl_pct`，它很可能是历史已完成交易，不应作为当前持仓/候选展示。

3. **接口必须同源**
   - `/api/picks`、`/api/live-prices`、`/api/summary` 必须读同一版本/同一语义源。
   - 常见错配：picks/live 使用 V103A active 文件，但 summary 仍读取 V102 trades；页面标签显示 V103A，但统计口径不是 V103A。
   - 实测接口，不能只看文件存在或页面标签。

4. **区分三类“未来函数/后验风险”**
   - 日期级未来函数：如 `zone_date > entry_date`，这是硬错误，必须从 clean 口径删除。
   - 时序语义污染：如 `entry_idx < reclaim_idx`，不一定是价格未来泄漏，但不能再声称“reclaim 确认后入场”；只能称为预埋限价 + 事后确认风险。
   - 后验筛选/幸存者偏差：如 `reachable_5r_probability_gate`、历史胜率 tier、production whitelist、基于历史 outcome 的白名单。这不一定是代码级未来函数，但不能作为真实 ex-ante 生产规则。

## 必查字段

### 数量/门禁字段
- `combo_contract_key`
- `combo_family`
- `conf_type`
- `production_eligible_*`
- `production_whitelist_*`
- `combo_candidate_whitelist_*`
- `v98_reachable_5r_gate`
- `v100_tier`
- `v102_balanced_volume_gate`
- `v103a_risk_gate`
- `pick_scope`
- `is_active_pick`

### 未来/后验风险字段
- `mfe_r`, `mae_r`
- `net_pnl_pct`, `pnl_pct`
- `exit_reason`, `exit_date`, `exit_idx`
- `hit_tp1`, `hit_tp2`
- `hold_bars`
- `planned_exit_*`
- `expected_tp*_net_pct`（必须确认是否由入场前结构目标计算，而非未来结果）

### 时序字段
- `sweep_idx`, `event_idx`, `zone_idx`, `touch_idx`, `reclaim_idx`, `entry_idx`, `exit_idx`
- `event_date`, `zone_date`, `pick_date`, `join_date`, `entry_date`, `exit_date`

## 判定标准

| 发现 | 结论 |
|---|---|
| 底层 1万+ 信号，但 production <2% | 不是信号缺失，是生产门/白名单压缩 |
| active 数量极少且均有 `exit_reason` | active 源语义错误：历史已完成样本被当当前候选 |
| `/api/picks` 与 `/api/summary` engine/version 不同 | 前端数据源错配 |
| `zone_date > entry_date` | 硬未来函数，必须删除或修正 |
| `entry_idx < reclaim_idx` 大量存在 | 入场语义不能称为 reclaim 后确认入场 |
| live-prices 对已 TP/SL 行继续按当前价算 PnL | 实时持仓语义错误，应按 monitor/ledger 状态过滤 |
| 生产门依赖历史 WR/tier/white-list | 后验筛选风险，需重新构造 ex-ante 规则 |
| V103A 文件存在但 `/api/summary` 返回 V102 | 前端 promoted 链路未真正晋级；检查 `_promoted_trade_file()`、`reload_metrics()` 是否优先读 `V103A_DIR/v103a_trades.json`、`V103A_DIR/v103a_report.json` |
| `/api/picks` 返回 `exit_date/exit_reason/net_pnl_pct` 的 active 行 | active 文件被历史完成交易污染；不能作为当前选股或 live-prices 输入 |
| `entry_idx < reclaim_idx` 大量存在 | 不能声称“reclaim 确认后入场”；只能命名为 `PRE_RECLAIM_ZONE_MID_LIMIT_ANTICIPATION` 或重建入场时序 |

## V103A 2026-06-18 实测故障模式

本次审计的具体可复用结论：

| 层级 | 实测发现 | 后续检查动作 |
|---|---|---|
| audit CSV | raw=171，clean=170，removed_by_risk_gate=22 | clean 只说明硬日期未来函数剔除，不证明生产链路闭环 |
| risk gate | removed 的 `risk_pct` 全部 <0.7；clean `risk_pct` 0.7015~1.2494 | 确认 `risk_pct` 是否纯入场前结构风险；不要用 WR/RR 证明门禁有效 |
| active picks | `/api/picks` 只剩 1 条 `002461.SZ`，但含 `exit_date=20260605`、`exit_reason=TP2_MAIN_HIT`、`net_pnl_pct=4.0104` | 已完成历史交易不得作为当前 active/watchlist |
| live-prices | 同一条 TP2 历史交易按 20260618 最后价重算为 `pnlPct=-10.33%` | live 只能读 monitor OPEN/NEXT_DAY_PENDING 或最新扫描候选，不能读已完成回测行 |
| summary | `/api/summary` 返回 `version=V102`、`engine=V102_BALANCED_VOLUME_GATE`、`total_trades=195` | promoted summary/trades 仍优先 V102，需追 `_promoted_trade_file()`、`reload_metrics()` |
| sequence | clean 中 `entry_idx < reclaim_idx` 为 161/170，`event_date > zone_date` 为 71/170，`zone_date > pick_date` 为 99/170 | 这是时序语义污染：不是简单价格未来函数，但“确认后入场”叙述不成立 |

快速定位代码时，优先看 `smc_unified.py`：
- `_promoted_trade_file()` 是否优先返回 V103A；若先判断 V102，则 summary/backtest 会继续读旧版本。
- `reload_metrics()` 是否优先返回 V103A report；若先判断 V102，则 `/api/summary` 会显示旧版本。
- `_merge_v91_shadow_picks()` + `v103a_active_picks.json` 是否把历史完成交易作为 active picks。
- `_api_live_prices()` fallback 是否在无 monitor OPEN 仓位时直接读 `get_active_picks()`；若 active 被历史污染，会把已 TP/SL 行按当前价重算。

## 报告方式

给 Lei 报告时使用短表格：
- “已证实 / 未证实 / 硬错误 / 语义风险” 分开。
- 不用 WR/RR 单独证明版本有效。
- 明确说哪些是代码级未来函数，哪些是后验筛选，哪些是前端/active 数据源语义错误。
- 不要把历史生产池说成“当前选股”。

## 修复方向

1. **先不改信号定义**，先修数据源语义：production、active、monitor、frontend 分离。
2. active/watchlist 应来自最新全市场扫描 + 未完成 monitor 状态，不应继承历史 TP2/SL 行。
3. summary/picks/live-prices 必须统一版本与口径。
4. 对 `entry_idx < reclaim_idx` 的系统，如果保留，应重命名为 “zone-mid limit anticipation”，不能声明“reclaim确认后入场”。
5. 生产门应由入场前可知的 SMC 结构字段表达，不能由历史胜率、未来 MFE/MAE、最终 TP/SL 结果倒推。
# V185 前端字段合同与实时页语义修复

## 触发场景

用于 SMC 前端/实时页出现以下问题时：

- 选股页缺少或未展示 `选股日期`、`加入日期`。
- 选股页/实时页 `Zone` 为空，尤其是引擎行下方只显示空值。
- 实时页 `成本线`、`波动` 为空。
- promoted 版本（例如 V185）已作为前端生产版本，但 `/api/live-prices` 仍按底层 `ACTIVE_VERSION=V88` 过滤监控仓位，导致当前生产候选被误当作旧版本或 fallback rows。
- active/watchlist 使用历史回测代表行，带有 `exit/pnl/won/hold_bars` 等 outcome 字段，污染“当前候选/实时监控”语义。

## 最小修复模式

1. 先确认当前前端生产标签：`FRONTEND_VERSION` 可能是 promoted 版本，底层 `ACTIVE_VERSION` 仍可能是 `V88`。
2. 字段合同统一走 `_apply_smc_field_contract()`：
   - 日期：`select_date`、`pick_date`、`join_date`、`pickDate`、`joinDate`。
   - Zone：`zone_type`、`zone_low`、`zone_high`、`zone`、`zoneType`。
   - 成本线：`cost_line`、`smart_money_cost`、`costLine`。
   - 波动：`volatility_pct`、`volatilityPct`、`volatility`、`risk_pct`。
3. `/api/live-prices` 的监控仓位过滤不能只匹配 `ACTIVE_VERSION`：
   - 应同时允许 `_position_engine(pos).startswith(ACTIVE_VERSION)`；
   - 以及 `FRONTEND_VERSION != ACTIVE_VERSION` 时 `_position_engine(pos).startswith(FRONTEND_VERSION)`。
4. daily rematerialize 脚本应清理 active rows 的 outcome 字段：
   - `exit_date`, `exit_idx`, `exit_price`, `exit_reason`, `hold_bars`, `mae_pct`, `mfe_pct`, `pnl_pct`, `rr_realized`, `won`, `partial_taken`。
   - active rows 表示当前候选/监控上下文，不应携带已知回测出场结果。

## 验证门禁

每次修复后必须跑闭环验证，而不是只看页面肉眼显示：

| 检查项 | 通过标准 |
|---|---|
| Python 语法 | `py_compile` 通过 |
| 全量生产回测/闭环 | active version 报告存在，步骤 returncode 全 0 |
| T+1 | 同日 entry/exit 违规为 0 |
| active outcome pollution | active rows 中 outcome 字段非空计数为 0 |
| `/api/picks` | 日期、Zone、成本线、波动字段缺失为 0 |
| `/api/live-prices` | 日期、Zone、成本线、波动字段缺失为 0 |
| `/monitor` HTML | 包含 `选股日期/加入日期/Zone/成本线/波动` 且无 Traceback |
| `/live` HTML | 包含 `选股日期/加入日期/Zone/成本线/波动` 且无 Traceback |

## 复测脚本形态

可用一个本地 Python smoke 脚本依次请求：

- `/api/picks`
- `/api/live-prices`
- `/monitor`
- `/live`

并统计字段缺失。字段缺失判断中 `zone_low/zone_high` 可以允许 0 作为数值字段例外，但 `zone/cost_line/smart_money_cost/volatility_pct/risk_pct/pick_date/join_date` 不应为空。

## 经验结论

- `FRONTEND_VERSION` 是用户看到的生产合同，`ACTIVE_VERSION` 可能只是 V88 外壳；实时页、监控仓位、API 字段合同必须尊重 promoted version。
- 当前候选/active/watchlist 不能使用历史已出场交易行伪装；如果为了前端展示复用历史 trades，必须明确标为 `HISTORICAL_BEST` 或隔离到历史页。
- 修字段不能只补 HTML。必须同时补 API JSON、字段合同、实时 live guard、闭环回归报告。
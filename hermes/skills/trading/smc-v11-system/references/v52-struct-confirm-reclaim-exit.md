# V52 结构破位二次确认 + Reclaim 出场机制

## 触发背景

当 SMC 系统出现：

- 方向判断基本正确；
- 2R/4R 之后被结构 stop 洗出；
- 90 日复盘显示后续继续上涨；
- `SOLD_EARLY_BY_STRUCTURE_STOP` 高；
- `LOW_90D_MFE_CAPTURE` 高；

不要优先继续优化信号或扩大止损。应先判断是否是 **结构退出过早**。

V51 证据：

```text
avg_90d_capture = 0.354
SOLD_EARLY_BY_STRUCTURE_STOP = 主要卖早来源
LOW_90D_MFE_CAPTURE = 32
```

根因不是入场方向错，而是：

```text
结构 stop 被 wick / 单日收盘短暂击穿后立即退出，后续价格 reclaim 并继续上涨。
```

## V52 最小修复原则

保持前面已验证链路不动：

- 信号快照同源；
- provenance 审计；
- sequence 审计；
- 2R 质量门禁；
- 原始 SL 硬止损；
- 小赢/低R/噪音亏损过滤；
- 前端 active version / API / K线 / 选股 / autopsy 同步。

只修改 runner 出场逻辑：

```text
原始 SL：intrabar 硬止损。
结构 stop：必须二次确认，不再一碰就卖。
```

## 结构破位二次确认规则

建议实现：

```python
pending_struct_break = None

# 原始SL仍硬止损
if stop <= sl + 1e-9 and low <= stop:
    exit_now('SL_HIT')

# 结构保护stop：第一次收盘跌破只标记 pending
elif stop > sl + 1e-9:
    if pending_struct_break is None:
        if close < stop:
            pending_struct_break = {
                'stop': stop,
                'date': date,
                'idx': j,
                'close': close,
            }
            exit_legs.append({'reason': 'STRUCT_PENDING_BREAK', ...})
        elif low < stop <= close:
            exit_legs.append({'reason': 'STRUCT_INTRABAR_RECLAIM', ...})
    else:
        pending_stop = pending_struct_break['stop']
        if close > pending_stop:
            exit_legs.append({'reason': 'STRUCT_RECLAIM', ...})
            pending_struct_break = None
        elif close < pending_stop:
            exit_now('STRUCT_CONFIRM_BREAK')
```

规则含义：

1. `SL_HIT` 仍然立刻执行，不能为了趋势牺牲风险控制；
2. 结构 stop 第一次跌破只记录 `STRUCT_PENDING_BREAK`；
3. 后续收回 pending stop 上方，记录 `STRUCT_RECLAIM` 并取消退出；
4. 再次收盘跌破 pending stop，才 `STRUCT_CONFIRM_BREAK`；
5. intrabar 下穿但收盘收回，记录 `STRUCT_INTRABAR_RECLAIM`；
6. 交易结束前不能留下 unresolved pending。

## 审计指标

V52 类修复必须额外统计：

```python
pending_unresolved = 0
with_reclaim = count(trade has STRUCT_RECLAIM or STRUCT_INTRABAR_RECLAIM)
total_reclaims = count(STRUCT_RECLAIM + STRUCT_INTRABAR_RECLAIM)
leg_counts = Counter(exit_leg.reason)
```

验收标准：

```text
pending_unresolved == 0
provenance fatal == 0
sequence violation == 0
release gate pass == true
hold_over_90 == 0
small_win_below_2 == 0
loss_inside_1pct == 0
win_rr_below_2r == 0
avg_90d_capture 不低于上版
```

V52 实测参考：

```json
{
  "n_trades": 59,
  "wr": 96.61,
  "avg_pnl": 23.817,
  "avg_realized_r": 4.86,
  "avg_90d_capture": 0.466,
  "pending_unresolved": 0,
  "with_reclaim": 18,
  "total_reclaims": 47,
  "LOW_90D_MFE_CAPTURE": 15
}
```

## 前端同步坑

当新增 V52/Vxx 版本时，不只改 `ACTIVE_VERSION`。必须同步：

- `ACTIVE_VERSION`；
- `ACTIVE_TRADE_FILE`；
- `ACTIVE_PICK_FILE`；
- `Vxx_DIR`；
- `get_version_trades()`；
- `get_all_picks_scoped()`/pick scope 逻辑；
- `/api/summary` 的 `dir_map`；
- `/api/summary` 的 `prefix_map`；
- `/api/kline_full` version 下拉；
- `/api/picks`；
- `/api/picks/contract`；
- `/autopsy` / `/live` 页面可访问性。

本次 V52 曾出现 `/api/summary` 连接被关闭，根因是新增 V52 后漏补：

```python
dir_map['V52'] = V52_DIR
prefix_map['V52'] = 'v52'
```

这种错误会导致服务端处理 `/api/summary` 时异常断连。新增版本时必须把 API map 作为发布门禁检查项。

## 建议的下一步分诊

如果 V52 后仍有 `SOLD_EARLY_NEXT_90D`，不要再只加 reclaim。下一层通常是：

```text
趋势状态分层 runner：主升段不按普通结构 stop 卖，而按趋势衰竭/高阶结构退出。
```

可作为 V53 方向：

- trend-state runner；
- higher-timeframe structure exit；
- reclaim 后的趋势延长模式；
- 不降低胜率前提下提升 MFE capture。

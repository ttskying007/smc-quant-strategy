# V52/V53 出场闭环：结构破位确认、reclaim 与趋势 runner

## 触发场景

当 90 日闭环复盘出现大量：

- `SOLD_EARLY_NEXT_90D`
- `SOLD_EARLY_BY_STRUCTURE_STOP`
- `LOW_90D_MFE_CAPTURE`

且 provenance / sequence / 信号准确性已通过时，问题优先定位到 **出场层级**，不要再先改信号定义或入场过滤。

## V52：结构破位二次确认 + reclaim

### 根因

V51 的 `STRUCT_HL_BREAK` 在 2R/4R 结构锁定后，一旦 intrabar 触碰结构 stop 就退出。逐笔复盘发现大量交易属于：

```text
wick/单日波动击穿结构位 → 被洗出 → 后续继续上涨
```

这不是入场错，而是把普通波动误判成结构破坏。

### 修复规则

结构保护 stop 不再“一碰就卖”：

```text
1. 原始 SL 仍然硬止损；
2. 结构 stop 被击穿后，不立即卖；
3. 第一次 close < structure stop → STRUCT_PENDING_BREAK；
4. 后续 close > pending stop → STRUCT_RECLAIM，取消卖出；
5. 再次 close < pending stop → STRUCT_CONFIRM_BREAK，确认结构破位退出；
6. intrabar 下穿但收回 stop 上方 → STRUCT_INTRABAR_RECLAIM。
```

### 验证指标

V52 相对 V51 的实际效果：

```text
WR: 91.53% → 96.61%
avg_pnl: 16.10% → 23.82%
avg_realized_r: 3.258R → 4.86R
avg_90d_capture: 0.354 → 0.466
LOW_90D_MFE_CAPTURE: 32 → 15
```

Reclaim 机制验证应统计：

```text
with_reclaim
STRUCT_PENDING_BREAK
STRUCT_RECLAIM
STRUCT_INTRABAR_RECLAIM
STRUCT_CONFIRM_BREAK
pending_unresolved == 0
```

如果没有统计这些事件，不能声称 reclaim 生效。

## V53：趋势状态分层 runner

### 根因

V52 后仍有大量 `SOLD_EARLY_NEXT_90D`，说明剩余卖早不是简单确认不足，而是部分标的进入主升趋势后仍用普通结构 stop 管理。

趋势 runner 的识别条件可以用：

```text
MA10 > MA20
close > MA20
MA20 上行
距离20日高点 < 8%
20日波段强度 > 3ATR
trend_score >= 4
high_water >= entry + 6R
```

满足后进入：

```text
TREND_RUNNER_PROMOTE
```

### 关键教训

实测发现，简单把趋势 runner 按 MA20 二次跌破或 8R 宽 trailing 退出，并不一定优于 V52；有时会把 V52 已锁住的收益回吐。V53 的机制价值是区分：

```text
1. 原 setup 主升段没吃完 → runner 出场问题；
2. exit 后形成二次行情 → 应做再入场机制，而不是原单死拿。
```

因此继续处理 `SOLD_EARLY_NEXT_90D` 时，不要盲目继续放宽持仓。先把每笔卖早拆成：

```text
连续主升未吃完
vs
exit 后很久形成新 SMC setup
```

第二类应进入 V54 “二次行情识别 / exit 后再入场”，不是继续扩大 runner。

## 必跑审计

每个版本完成后必须同步跑：

```bash
python3 v25/vXX_engine.py
python3 v25/vXX_quality_metrics.py
python3 v25/vXX_trade_provenance_audit.py
python3 v25/vXX_signal_sequence_audit.py
python3 v25/vXX_closed_loop_90d_review.py
python3 v25/vXX_sample_bias_audit.py
python3 v25/vXX_monitor_journal.py
python3 v25/vXX_release_gate.py
```

门禁必须至少检查：

```text
provenance fatal_count == 0
sequence violation_count == 0
hold_over_90_count == 0
small_win_below_2_count == 0
loss_inside_1pct_noise_count == 0
win_rr_below_2r_count == 0
avg_90d_capture 达标
sample_not_too_narrow
```

## 前端同步要求

候选提升默认时，必须同步：

```text
ACTIVE_VERSION
ACTIVE_TRADE_FILE
ACTIVE_PICK_FILE
版本目录常量
get_version_trades
get_version_picks
get_engine_paths
/api/summary dir_map/prefix_map
/api/kline_full ver 支持
HTML version dropdown
```

特别注意：`/api/summary` 里即使外层 `if req_ver in (...)` 已加入新版本，也要同步 `dir_map` 和 `prefix_map`。漏掉会导致前端 `RemoteDisconnected`，服务端日志出现：

```text
KeyError: 'VXX'
```

验证命令模式：

```bash
python3 -m py_compile smc_unified.py
python3 smc_unified.py
# then verify:
/api/summary
/api/picks/contract
/api/picks
/api/kline_full?symbol=002440.SZ&tf=daily&ver=VXX
/autopsy
/live
```

前端验收必须确认：

```text
summary.version == VXX
active_default == VXX
/api/picks 返回非空 active picks
/api/kline_full 返回 signal_count/trade_count/highlight
页面正文没有 Traceback
```

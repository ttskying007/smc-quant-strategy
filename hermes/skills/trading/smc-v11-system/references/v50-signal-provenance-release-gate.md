# V50 信号同源与 Release Gate 修复经验

本参考记录 SMC V50 信号准确性闭环中形成的可复用流程。适用于后续 V51+ 或任意“信号定义/实现/回测/选股/K线前端不同步”的修复。

## 触发场景

用户指出：
- SMC 信号不准确，尤其 OB/FVG/结构信号与 Pine 图上不一致；
- 回测交易、选股、K线标识、分析复盘使用的不是同一套信号；
- 盈亏比过低，聚合胜率好看但逐笔机制未验证；
- 前端 K线图标、回测、选股、监控没有同步。

## 核心原则

1. **不要直接覆盖生产版本**：新建候选版本目录，如 `smc_opt_v50/` 与 `smc_opt_v50_signal/`。
2. **先建单一信号事实源**：生成全市场 signal snapshot，K线、回测、选股、审计全部读同一个 snapshot。
3. **每笔交易必须有 provenance**：至少包含 `source_event_id/zone_id/conf_id/entry_id/exit_id` 或对应 index。
4. **聚合 WR/RR 不能替代逐笔审计**：必须输出 fatal_count、sequence violations、低2R、小赢、噪音亏、90日 MFE capture。
5. **候选版本必须 release gate 卡关**：不通过就不能切默认 production。

## 推荐 Phase 流程

### Phase 1 — Signal Snapshot

生成：
- `vXX_signal_snapshot.json`
- `vXX_signal_report.json`
- `vXX_pine_param_matrix.json`

字段建议：
```json
{
  "symbol": "000001.SZ",
  "idx": 123,
  "date": "20260525",
  "family": "ob|fvg|structure|sweep|swing|ote|eql|bpr|lv",
  "type": "OB_Bull",
  "signal_id": "000001.SZ:ob:OB_Bull:20260525:123",
  "price": 10.5,
  "lower": 10.1,
  "upper": 10.8
}
```

K线 API 必须支持 `ver=VXX` 直接读取 snapshot，而不是请求时临时计算另一套信号。

### Phase 2 — Trade Provenance Audit

每笔交易检查：
- source event 是否存在；
- zone 是否存在；
- confirmation 是否来自同源 snapshot 或明确 execution marker；
- entry/exit 是否有 index 和 date；
- 时间顺序是否满足：

```text
source_event_idx <= zone_idx <= retrace_index <= conf_index <= entry_index <= exit_index
```

如果 `conf_index` 是执行确认而不是 Pine raw signal，必须写显式 marker：

```text
symbol:confirm:CONFIRM_EXECUTION:entry_date:entry_index
symbol:entry:ENTRY_EXECUTION:entry_date:entry_index
symbol:exit:exit_reason:exit_date:exit_index
```

否则审计器会错误地用“最近 raw signal”判断 bar_diff。

### Phase 3 — 质量 Gate

正式 trade 文件不要混入低质量小赢。候选被剔除时保留到 picks/setup 中做复盘，不要丢证据。

硬 gate：
- `win_rr_below_2r == 0`
- `small_win_below_2 == 0`
- `loss_inside_1pct == 0`
- `hold_over_90 == 0`
- `provenance_fatal_count == 0`
- `sequence_violation_count == 0`

低质量候选标记：
```text
REJECTED_CANDIDATE
reject_reason = WIN_RR_BELOW_2R | WIN_BELOW_2PCT_FEE_INEFFICIENT | LOSS_BELOW_1PCT_NOISE_EXIT
```

### Phase 4 — 结构化出场注意事项

结构 stop 容易卖早。不要只要跌破 HL/OB low 就卖。至少要满足：
- 已经达到合格保护线 `max(2%, 2R)`；或
- 原始 SL 被打；
- 更优版本再加入 close break + no reclaim / reverse CHOCH / demand invalidation。

如果 90 日复盘出现：
```text
SOLD_EARLY_NEXT_90D 很高
SOLD_EARLY_BY_STRUCTURE_STOP 很高
LOW_90D_MFE_CAPTURE 很高
```
说明 runner 仍然过早退出，下一步应优化出场确认，而不是继续调信号入口。

### Phase 5 — 多池选股

不要只把历史已成交交易当当前选股。至少输出：
- `ACTIVE_ENTRY`
- `NEAR_ZONE_WATCH`
- `POST_ENTRY_MONITOR`
- `EXPIRED_REVIEW`
- `REJECTED_CANDIDATE`

当 `ACTIVE_ENTRY` 很少时，从近期 OB/FVG zone 生成 `NEAR_ZONE_WATCH`，避免监控池过窄。

### Phase 6 — Release Gate

建议输出：
- `vXX_release_gate.json`
- `vXX_release_gate.md`

最小检查项：
```text
trade_file_exists
pick_file_exists
signal_snapshot_exists
provenance_fatal_count_zero
sequence_violations_zero
hold_over_90_zero
small_win_below_2_zero
loss_inside_1pct_zero
win_rr_below_2r_zero
sample_not_too_narrow
mfe_capture_threshold
```

注意：MFE capture 门槛不能随意放宽为“通过而通过”。如果降低门槛，必须在报告里明确写出它只是候选合格，不代表 runner 已优化完成。

## 关键反模式

- 只改后端，不验证 K线 API `ver=VXX`。
- 只看 WR/RR，不看逐笔 `realized_r` 与 90日 MFE capture。
- 把低2R盈利算作胜利。
- 把历史交易伪装成当前 active picks。
- 用另一套临时计算信号画 K线，回测使用旧交易字段。
- release gate 失败后直接切 production。

## 验证命令模板

```bash
cd /root/.hermes/scripts
python3 v25/vXX_signal_snapshot.py
python3 v25/vXX_engine.py
python3 v25/vXX_quality_metrics.py
python3 v25/vXX_trade_provenance_audit.py
python3 v25/vXX_signal_sequence_audit.py
python3 v25/vXX_closed_loop_90d_review.py
python3 v25/vXX_sample_bias_audit.py
python3 v25/vXX_monitor_journal.py
python3 v25/vXX_release_gate.py
```

前端 smoke test：
```bash
python3 - <<'PY'
import urllib.request,json
base='http://127.0.0.1:8890'
for ep in ['/api/summary','/api/picks','/api/kline_full?symbol=002510.SZ&tf=daily&ver=VXX','/autopsy','/live']:
    data=urllib.request.urlopen(base+ep,timeout=30).read().decode('utf-8','ignore')
    print(ep, len(data), 'Traceback' in data)
PY
```

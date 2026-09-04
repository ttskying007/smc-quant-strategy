# V60 闭环复盘与前端版本同步教训

## 背景
V60 已经有完整交易 provenance 字段，但闭环复盘和前端仍沿用早期 V49/V47 的假设，导致两类误判：

1. `/api/autopsy/closed-loop` 固定读取 `v49_closed_loop_90d_review.json`，当前 active version 为 V60 时仍展示旧报告。
2. 闭环复盘用 `wave_ref/struct_event` 判断信号 trace 是否存在，V60 交易没有这两个嵌套字段，但有完整索引链：`source_event_idx / zone_idx / conf_index / entry_index / exit_index`，因此误报 `SIGNAL_TRACE_MISSING_FRONTEND_AUDIT`。
3. V60 trades 没有传统 `entry_mode`，但有 `v59_setup_family/trade_role`；复盘按 entry_mode 分桶时会全部落入 `None`。

## durable fix pattern

### 1. 前端闭环复盘必须按 ACTIVE_VERSION 读取
不要把 autopsy/closed-loop 固定到某个旧版本文件。应按当前 active version 构造候选路径，并保留旧版本 fallback：

```python
def _load_v49_closed_loop_review():
    version_key = str(ACTIVE_VERSION).lower().replace('_', '_')
    candidates = [
        Path(f'/root/.hermes/smc_audit/{version_key}_closed_loop_90d_review.json'),
        Path('/root/.hermes/smc_audit/v49_closed_loop_90d_review.json'),
    ]
    for p in candidates:
        if p.exists():
            return _load_json_dict(p, {})
    return {}
```

命名可保留旧函数名以减少改动，但实现必须 active-version aware。

### 2. Signal trace 存在性判断要兼容 provenance 索引链
V60/V59 交易可能没有 `wave_ref/struct_event`，不能据此判定 trace 缺失。使用完整索引链作为等价 proof：

```python
provenance_keys = ('source_event_idx', 'zone_idx', 'conf_index', 'entry_index', 'exit_index')
has_signal_trace = bool(
    t.get('wave_ref')
    or t.get('struct_event')
    or all(i(t.get(k)) >= 0 for k in provenance_keys)
)
if not has_signal_trace:
    issues.append('SIGNAL_TRACE_MISSING_FRONTEND_AUDIT')
```

### 3. entry_mode 分桶要 fallback 到 setup family
V60 的实际入场类别是 family 级别：`PRIMARY_SETUP / CONTINUATION_SETUP / REENTRY_SETUP`。闭环复盘返回 rows 时应使用：

```python
'entry_mode': (
    t.get('entry_mode_v47_1')
    or t.get('entry_mode')
    or t.get('v59_setup_family')
    or t.get('trade_role')
)
```

## verification checklist
修改后必须重新跑全套审计，而不是只改前端：

```bash
cd /root/.hermes/scripts
python3 v25/v60_quality_metrics.py
python3 v25/v60_trade_provenance_audit.py
python3 v25/v60_signal_sequence_audit.py
python3 v25/v60_sample_bias_audit.py
python3 v25/v60_closed_loop_90d_review.py
python3 v25/v60_release_gate.py
```

验收条件：

- release gate `pass == true`
- provenance `fatal_count == 0`
- sequence `violation_count == 0`
- closed-loop reviewed trades 与 V60 trade count 对齐
- `SIGNAL_TRACE_MISSING_FRONTEND_AUDIT` 不再出现在 issue_counts 中（除非真实缺索引）
- `/api/autopsy/closed-loop` 返回当前 ACTIVE_VERSION 的报告，不是旧版本报告
- `by_entry_mode` 不应只有 `None`，应能看到 setup family 或真实 entry mode 分桶

## pitfall
不要把“缺少 wave_ref/struct_event”当成信号追踪缺失。V60 的审计事实来源是 provenance indices + ids；前端/K线可以再 enrichment，但 release gate 与闭环复盘不能因此误判。

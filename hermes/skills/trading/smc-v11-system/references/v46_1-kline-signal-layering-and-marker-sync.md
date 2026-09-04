# V46.1 K线信号分层与标识同步经验

## 触发场景

用户反馈 SMC 信号在 K 线图上不准确，尤其 BOS / CHOCH / MSS / OB 与 Pine 图形不一致，要求前端标识同步用于肉眼校验。

## 核心问题

1. **internal 与 swing 层级坍缩**
   - 错误形态：`swing_len == internal_len == 5`
   - 结果：internal MSS 与 swing CHOCH/BOS 在同一 bar 重复出现，K线图看起来“信号很多但不准”。

2. **MSS 语义混入 swing structure**
   - MSS 应作为 internal early warning，而不是和 swing BOS/CHOCH 平级重复生成交易结构。

3. **OB 来源污染**
   - 如果 OB 从 `swing_struct + internal_mss` 生成，会把 internal early-warning 误当成可交易 OB 来源。
   - 修复：OB 只从 swing structure 生成；internal MSS 只用于提示。

4. **前端标识不够可审计**
   - `CH` 这类缩写无法让用户肉眼判断方向和类型。
   - 应在 K 线标记中直接显示：`BOS↑ / BOS↓ / CHOCH↑ / CHOCH↓ / MSS↑ / MSS↓ / LIQ / OB / FVG`。

## 修复规则

### 信号核心

在 `smc_core_luxalgo_v34.py` 中：

```python
def detect_all_signals_lux_v34(klines, swing_len=5, internal_len=3):
    swing_struct = display_structure_lux(... swing ...)
    internal_struct = display_structure_lux(... internal ...)
    qualify_mss(swing_struct, sweeps, klines, atr)
    qualify_mss(internal_struct, sweeps, klines, atr)

    # internal 只贡献 MSS early warning，且不能重复 swing 同 bar/方向/类型事件
    swing_keys = {(e['index'], e['direction'], e['type']) for e in swing_struct}
    internal_mss = []
    for e in internal_struct:
        if not e.get('is_mss'):
            continue
        if (e.get('index'), e.get('direction'), e.get('type')) in swing_keys:
            continue
        e['type'] = 'MSS'
        e['is_internal_mss'] = True
        internal_mss.append(e)

    structure = sorted(swing_struct + internal_mss, key=lambda x: x['index'])
    obs = order_blocks_from_structure(klines, swing_struct, atr)
```

### 前端 K线标识

在 `smc_unified.py` 的 `buildSignalPoints()` 中，信号标签应使用方向明确版本：

```javascript
var seqLabels = {
  'CHOCH_Bull':'CHOCH↑', 'CHOCH_Bear':'CHOCH↓',
  'BOS_Bull':'BOS↑',     'BOS_Bear':'BOS↓',
  'MSS_Bull':'MSS↑',     'MSS_Bear':'MSS↓',
  'Sweep_SSL':'LIQ',     'Sweep_BSL':'LIQ',
  'OB_Bull':'OB',        'OB_Bear':'OB',
  'FVG_Bull':'FVG',      'FVG_Bear':'FVG'
}
```

在 `_api_kline_full()` 渲染 structure event 时：

```python
# Internal MSS already has base_type == 'MSS'; do not append another MSS marker.
if ev.get('is_mss') and base_type != 'MSS':
    append_extra_mss_marker()
```

## 必须验证

每次修改后必须至少验证：

```text
python3 -m py_compile /root/.hermes/scripts/v25/smc_core_luxalgo_v34.py /root/.hermes/scripts/smc_unified.py
```

再调用 K线 API：

```text
/api/kline_full?symbol=600519.SH&ver=V46_1
```

检查：

- `structure_duplicates == 0`
- 返回信号包含 `CHOCH_Bull/Bear`、`BOS_Bull/Bear`、`MSS_Bull/Bear`
- 前端 HTML/JS 或 ECharts option 中存在：`CHOCH↑ CHOCH↓ BOS↑ BOS↓ MSS↑ MSS↓`
- K线图上 `LIQ` 必须显示标签，不能只画无字三角形。

## 用户偏好

Lei 会直接肉眼检查 K线图，不接受只报聚合指标。SMC 修复必须优先保证：

1. K线图标识和后端信号源同源。
2. 每个修复都有 API/图表层验证。
3. 不把 WR/RR 优化当成信号正确性的替代证明。
4. 不给用户选项；自主完成修复、重启、验证。
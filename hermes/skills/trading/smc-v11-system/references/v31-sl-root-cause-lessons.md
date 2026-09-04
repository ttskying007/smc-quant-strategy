# V31 止损集中触发根因排查经验（2026-05-22）

## 触发场景

用户发现止损触发较多，要求全面判断到底是：

- SMC 信号定义问题
- 信号组合方式问题
- 入场点问题
- 未真正到入场点位就入场
- 止损参数问题

本经验适用于后续所有 SMC 引擎止损率异常、SL hit 集中、胜率下降、或用户质疑“是不是信号/入场点定义错了”的排查。

## 核心结论

止损集中时不要先调宽 SL。V31 排查显示：

1. 亏损组 `risk_pct` 反而更大，说明不是止损太紧。
2. 更主要的问题是入场链路过早完成：亏损组从 zone/event 到 entry 的 bar 数明显短于盈利组。
3. zone touch / confirmation 定义过宽会导致“zone 已经跌破后仍被当成 RTO 成功”。
4. BPR 即使文档标记禁用，也必须全局检查实际交易日志里是否仍有 `zone_type == BPR`。
5. OTE 不应作为独立主 POI；它更像折价区域，必须和 OB/FVG overlap 或强共振一起使用。

## 必查维度

止损归因必须按以下顺序做，不允许只报聚合 WR/RR：

1. **结果切片**
   - SL / TP / TIME_STOP 数量
   - SL 组 vs WIN 组的 `risk_pct`, `rr`, `pnl_pct`, `hold_bars`

2. **链路成熟度**
   - `entry_idx - zone_idx`
   - `source_event_idx - sweep_idx`
   - `entry_idx - source_event_idx`
   - 对比 SL 组与 WIN 组均值/分位数

3. **是否未到入场点位**
   - entry 是否仍在 zone 边界内或合理 tolerance 内
   - confirmation close 是否重新站回 zone_low
   - T+1 open 是否低于 zone_low 太多

4. **zone 是否已失效**
   - retrace candle 是否真实 overlap zone
   - confirmation 前后是否 close 跌破 zone_low
   - entry 前是否重新检查 zone invalidation

5. **信号定义审计**
   - OB/FVG/BPR/OTE 分类型统计 SL 率
   - Pinbar/BR 是否只是确认，不能作为独立起点
   - Sweep 方向是否正确：bull 用 wick_low，bear 用 wick_high

6. **组合方式审计**
   - SSL → MSS/CHOCH → POI → RTO → Pinbar/BR 的时间顺序是否真实成立
   - 是否存在窗口集合式“凑信号”
   - 是否存在 source event 太旧、zone 太新、confirmation 太快的伪序列

## V31 暴露的典型代码缺陷

问题代码形态：

```python
wick_touches_zone = lo <= zh * 1.005
not_full_break = cl >= zl * 0.97
candle_at_zone = lo <= zh * 1.01
```

缺陷：

- 没要求 `hi >= zone_low`，导致并未真实 overlap zone。
- 允许 close 跌破 zone_low 3% 后仍算有效。
- confirmation 没要求收盘重新站回 zone_low。
- retrace 后、confirmation/entry 前没有重新检查 zone 是否失效。

## 推荐修复规则

用于下一版严格 RTO validation：

```python
real_touch = lo <= zh * 1.005 and hi >= zl * 0.995
retrace_valid = cl >= zl * 0.995
confirmation_at_zone = hi >= zl * 0.995 and lo <= zh * 1.01 and cl >= zl * 0.995
entry_valid = entry_price >= zl * 0.995
```

BPR 必须全局禁止：

```python
if st.get('zone_type') == 'BPR':
    continue
```

链路成熟度门控示例：

```python
zone_age = entry_idx - zone_idx
sweep_to_event = source_event_idx - sweep_idx
if zone_age <= 5:
    continue
if sweep_to_event > 12:
    continue
```

OTE 降级：

- OTE 不作为独立主 POI。
- 只有当 OTE 与 OB/FVG overlap，或有强 market/resonance 共振时，才允许参与入场。

## 输出要求

向 Lei 汇报这类排查时：

- 先给结论：到底是信号、组合、入场、点位、还是 SL 参数。
- 必须给 SL 组 vs WIN 组的数值对比。
- 必须指出代码级根因和文件位置。
- 必须给可执行修复规则。
- 不要只说“胜率仍然高”或“参数需要优化”；这不满足用户对机制验证的要求。

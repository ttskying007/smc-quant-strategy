# V46.1 Pine/LuxAlgo 结构语义对齐：MSS、bootstrap、OB/FVG 边界

## 触发场景

当用户质疑 SMC BOS/CHOCH/MSS/OB/FVG 信号“不像 Pine”“图上不准”“交易/选股受影响”时，不能只看 WR/RR。必须按下面链路审计：

1. 信号定义是否与 Pine/LuxAlgo 参数一致
2. 结构事件是否满足时间顺序与 crossover/crossunder 不变量
3. 图表层标识与交易层门槛是否被混用
4. setup 保留/拒绝原因是否可解释
5. 回测、选股、K线标识、前端 API 是否同步

## 关键语义结论

### 1. `is_mss` 与 `is_mss_confirmed` 必须拆开

Pine/LuxAlgo 的 MSS 常是 early-warning 图表语义，不等于可交易 reversal 确认。

推荐语义：

```python
is_mss = event.type == 'CHOCH' and recent_same_direction_sweep
is_mss_confirmed = is_mss and displacement_or_stronger_confirmation
```

使用规则：

- K线图/结构标签：使用 `is_mss`，用于显示 `MSS_Bull/MSS_Bear`
- 交易 reversal 入场：使用 `is_mss_confirmed`
- 未确认 MSS 不应静默丢弃，要计入 reject counter，例如 `REVERSAL_MSS_NOT_CONFIRMED`

避免错误：

```python
# 错误：把 early-warning MSS 直接当交易门槛
if ev.get('type') == 'CHOCH' and ev.get('is_mss'):
    enter_reversal()
```

正确：

```python
if ev.get('type') == 'CHOCH' and ev.get('is_mss_confirmed'):
    enter_reversal()
elif ev.get('type') == 'CHOCH':
    rejects['REVERSAL_MSS_NOT_CONFIRMED'] += 1
```

BOS 是 continuation context，不应强制要求 `is_mss`：

```python
if ev.get('type') == 'BOS':
    # continuation context; not reversal/MSS trigger
    pass
```

### 2. `bootstrap_cutoff` 不应使用 `size * 2`

在 LuxAlgo/Pine 风格 leg/pivot 检测里，`bootstrap_cutoff = size * 2` 会额外吞掉已经确认的 pivot，导致 BOS/CHOCH/MSS 低估。

更贴近 Pine 的默认：

```python
bootstrap_cutoff = size
```

修完必须跑结构审计，确认：

- event index 晚于 pivot index
- BOS/CHOCH 使用 close crossover/crossunder
- MSS 必须来自 CHOCH + recent sweep
- bad_events = 0

### 3. Pine 截图参数对齐点

用户给过的 Pine/LuxAlgo 参数里，对 SMC 结构影响最大的有：

- Swing Length = 5
- OB Swing Detection Length = 7
- OB Lookback = 10
- OB Displacement Multiplier = 1.5
- EQH/EQL Pivot Length = 4
- EQH/EQL Threshold = 0.1
- Minimum Strength Filter = 3
- LuxAlgo Internal/Swing Order Blocks = 5

落地到 Python profile 时，优先检查：

```python
swing_len = 5
eq_len = 4
ob_backscan = 10
ob_displacement_mult = 1.5
```

注意重复配置键会覆盖前值，例如同一 dict 里同时出现：

```python
'ob_backscan': 10,
...
'ob_backscan': 15,
```

实际生效的是 15，会导致视觉 OB 与 Pine Lookback 10 不一致。

### 4. FVG raw 边界不要乱改

Pine 三蜡烛 FVG 的基础边界通常是：

```python
# bullish FVG
if high[i-2] < low[i]:
    gap_low = high[i-2]
    gap_high = low[i]

# bearish FVG
if low[i-2] > high[i]:
    gap_low = high[i]
    gap_high = low[i-2]
```

不要为了回测指标随意改成 midpoint/display zone。若 FVG 交易表现差，优先检查：

- gap 是否过宽
- 是否远离流动性目标
- 是否缺少回撤确认
- 是否处于中位流动性陷阱区间
- 是否被 continuation/reversal 分类误用

## 验证流程

### A. 语法

```bash
python3 -m py_compile \
  smc_core_luxalgo_v34.py \
  smc_core_pine_like.py \
  v34c_next_open.py \
  v45_1_recall_repair.py \
  v46_1_layered_3y.py
```

### B. 结构审计

```bash
cd /root/.hermes/scripts/v25
python3 v46_1_structure_audit.py
```

通过标准：

```json
{
  "bad_events": 0,
  "errors_count": 0
}
```

同时记录 BOS/CHOCH/MSS 数量变化，不能只报通过。

### C. 机制抽样

至少检查：

- `CHOCH non-MSS`
- `MSS early-only`
- `MSS confirmed`
- `BOS continuation`
- `REVERSAL_MSS_NOT_CONFIRMED` reject 桶

确认交易层只吃 confirmed MSS，而 K线层仍显示 early MSS。

### D. 全量回测重建

```bash
cd /root/.hermes/scripts/v25
python3 v46_1_layered_3y.py --rebuild-base
```

输出后读取：

- trade 数
- WR
- SL rate
- avg pnl / RR
- reject counters
- watchlist / picks 数
- problem samples

### E. 前端同步

回测产物更新后必须验证：

```bash
curl -s http://127.0.0.1:8890/api/reload
curl -s http://127.0.0.1:8890/api/picks?ver=V46_1
curl -s http://127.0.0.1:8890/monitor
curl -s 'http://127.0.0.1:8890/api/kline_full?symbol=000006.SZ&tf=daily&ver=V46_1'
```

必须确认：

- `/api/reload` 的 trades/picks/watchlist 数与新产物一致
- `/api/picks` 字段完整：日期、entry、SL、TP、quality、sequence/source_event
- `/monitor` 使用 active watchlist，不用历史 trades 伪装当前选股
- K线 `signals_list` 包含 BOS/CHOCH/MSS/OB/FVG/Sweep，且 family 样式映射存在

## 报告要求

给用户报告时按“定义→实现→验证→影响→剩余差距”写，不要只给聚合指标：

1. 哪些 Pine 参数已对齐
2. 哪些代码点被修
3. 修复前后 BOS/CHOCH/MSS 数量变化
4. trade/WR/SL/RR 变化
5. 逐笔问题样本的 reject 原因
6. K线标识与前端 API 是否同步
7. 是否真正对标 Pine：已对齐项与仍未完全对齐项分别列明

不要声称“完全对标 Pine”，除非结构定义、参数、图表显示、交易消费链、前端同步、全量审计与逐笔样本都已验证。

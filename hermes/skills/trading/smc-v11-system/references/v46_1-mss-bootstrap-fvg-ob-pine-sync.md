# V46.1 Pine/LuxAlgo MSS、bootstrap、前端同步修复记录

## 触发场景
用户指出 SMC 信号不准确，尤其 BOS/CHOCH/MSS、OB/FVG、回测、选股和 K 线标识同步存在联动问题。后续要求继续修：

1. `v34c_next_open.py` 交易门槛区分 `is_mss` / `is_mss_confirmed`
2. 拆 `bootstrap_cutoff`
3. OB/FVG 做 Pine 级对齐
4. 全量回测、逐笔复盘、前端同步验证

## 核心修复

### 1. MSS 语义必须分层
不要把图表 MSS 预警信号直接作为交易 reversal 触发。

- `is_mss`: 图表层 / Pine-LuxAlgo early-warning，含 CHOCH + recent sweep。
- `is_mss_confirmed`: 交易层强确认，要求 sweep + displacement 等更严格条件。

在 `v34c_next_open.py` 中：

```python
if ev.get('type') == 'BOS':
    # BOS is continuation context, not a reversal/MSS trigger.
    continue

if ev.get('type') == 'CHOCH' and not ev.get('is_mss_confirmed'):
    continue
```

注意 V46.1 全量回测实际链路不一定走 `v34c_next_open.py`，还要同步 `v45_1_recall_repair.py`：

```python
if ev.get('type')=='CHOCH' and ev.get('is_mss_confirmed'):
    families.append(('REVERSAL', sw, ev['index']-sw['index']))
elif ev.get('type')=='CHOCH':
    rejects['REVERSAL_MSS_NOT_CONFIRMED'] += 1
```

并且 `seq/ctx_seq/source_event` 应显示 `MSS`，不能仍显示原始 `CHOCH`，否则前端、复盘、问题桶会误导。

### 2. bootstrap_cutoff
原逻辑：

```python
bootstrap_cutoff = size * 2
```

修为：

```python
bootstrap_cutoff = size
```

原因：`size * 2` 不是 Pine/LuxAlgo leg 规则，会额外吞掉一个已确认 pivot。对 `Swing Length = 5` 会造成早期 BOS/CHOCH/MSS 缺失。修复后全市场结构事件从约 201501 增至 206608，bad_events 仍为 0。

### 3. Pine 参数对齐
从用户截图/OCR 提取的参数：

- Swing Length = 5
- OB Swing Detection Length = 7
- OB Lookback = 10
- OB Displacement Multiplier = 1.5
- EQH/EQL Pivot Length = 4
- EQH/EQL Threshold = 0.1
- Minimum Strength Filter = 3

实际修复中至少要保证：

```python
'eq_len': 4,
'ob_backscan': 10,
'ob_displacement_mult': 1.5,
```

检查是否存在重复 key 覆盖，例如早期 `smc_core_pine_like.py` 里 `ob_backscan` 同时出现 10 和 15，后者会静默覆盖前者。

### 4. FVG 边界
Pine 三蜡烛 bullish FVG raw 边界保持：

```python
gap_low = high[i-2]
gap_high = low[i]
```

不要把 raw structural boundary 改成 midpoint/execution zone。应保持 raw/display 边界与 execution subzone 分离：

- raw zone：结构真实边界，用于图表、结构无效判断。
- execution zone：交易执行子区，用于入场价格控制。

若仍出现 `FVG_NOT_PINE_PARAM_OR_BOUNDARY_SHIFT`，优先排查 raw/display/execution 字段混用，而不是改三蜡烛定义。

## 验证流程

### 1. 全量结构审计
运行结构审计后必须达到：

```json
{
  "files": 4649,
  "bad_events": 0,
  "bad_rate": 0.0,
  "errors_count": 0
}
```

示例修复后分布：

```json
{
  "BOS bear swing": 42018,
  "BOS bull swing": 36797,
  "CHOCH bull non-MSS": 27271,
  "CHOCH bear non-MSS": 24852,
  "CHOCH bull MSS": 17851,
  "CHOCH bear MSS": 19984
}
```

### 2. 全量回测
运行：

```bash
cd /root/.hermes/scripts/v25
python3 v46_1_layered_3y.py --rebuild-base
```

修复后一次参考结果：

- base trades: 9384
- kept trades: 825
- kept WR: 81.6%
- kept SL rate: 18.1%
- weighted WR: 84.2%
- weighted SL rate: 15.4%
- weighted avg PnL: 6.53

这些数字不是永久目标，只作为 sanity check。更重要的是结构审计、问题桶、逐笔复盘。

### 3. 前端同步
重启 8890 后验证：

```bash
curl -s http://127.0.0.1:8890/api/reload
curl -s http://127.0.0.1:8890/api/picks
curl -s http://127.0.0.1:8890/monitor
```

期望：

- `/api/reload` 的 trades/picks/active_pick_count 与新产物一致。
- `/api/picks` 返回 `ACTIVE_CANDIDATE`，不是历史交易污染。
- `/monitor` 显示 `V46_1 当前有效选股 — N只`。

### 4. K线结构标识
在 `smc_unified.py` 的 `buildSignalPoints()` 中，点位标签必须覆盖 bull/bear 两侧：

```js
'CHOCH_Bull':'CH','CHOCH_Bear':'CH',
'BOS_Bull':'BOS','BOS_Bear':'BOS',
'MSS_Bull':'MSS','MSS_Bear':'MSS',
'FVG_Bull':'FVG','FVG_Bear':'FVG',
'Pinbar_Bull':'PB','Pinbar_Bear':'PB'
```

仅 `SIG_STYLE`/`SIG_FAMILY` 支持不够；如果 `seqLabels` 漏掉 `BOS_Bear` 或 `MSS_Bear`，K线表层仍会显示不一致。

用接口抽查：

```bash
curl 'http://127.0.0.1:8890/api/kline_full?symbol=000006.SZ&tf=daily&ver=V46_1'
```

检查 `signals_list` 里是否同时有 `bos/choch/mss/ob/fvg/sweep` family，且 highlight 链路存在。

## 问题桶解释

修复后如果仍有问题，优先看这些桶：

1. `LIQUIDITY_TARGET_TOO_CLOSE_OR_MISSING`：盈亏比低主因，说明上方流动性/目标空间不足。
2. `OB_NOT_VISUAL_SMC2026_ZONE`：OB 视觉框仍和 Pine/SMC2026 有差异，优先检查 swing 附近 OB、overlap、mitigation，而不是只调 WR。
3. `FVG_NOT_PINE_PARAM_OR_BOUNDARY_SHIFT`：多半是 raw/display/execution 字段混用，不一定是三蜡烛定义错。
4. `FVG_TOO_WIDE`：不要靠放宽止损解决；先做宽度、流动性目标、touch mitigation 分诊。
5. `CONFIRM_NOT_TWO_BAR_REJECTION_HOLD`：weak reclaim/pinbar 不能作为独立高质量入场确认。

## 用户偏好嵌入

处理 Lei 的 SMC 系统时，不要只报聚合 WR/RR。必须按顺序交付：

1. 结构定义是否正确
2. 实现代码是否对齐 Pine/LuxAlgo
3. 回测交易是否使用同一语义
4. 选股、K线、复盘、分析是否同步
5. 全量审计和逐笔问题样本
6. 再谈 WR、SL、RR 和盈亏比

用户会检查机制是否真的执行，而不是只看数字是否好看。
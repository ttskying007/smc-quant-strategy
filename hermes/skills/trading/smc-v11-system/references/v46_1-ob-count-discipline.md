# V46.1 OB数量膨胀审计与修复

## 触发场景

用户反馈：`OB的数量又多了一些`、K线图 OB 标记过密、选股/回测/reversal/REJECT 中 OB 数量不一致，或 OB 明显偏离 Pine/LuxAlgo 效果图。

## 核心结论

OB 数量过多时，不要先调选股过滤或删除前端标记。先分清 4 个入口的 OB 来源：

1. **K线展示 OB**：通常来自 `smc_core_luxalgo_v34.detect_all_signals_lux_v34()`，直接影响图表标识数量。
2. **回测交易 OB**：来自 V46.1 base trades / kept trades，已经经过 entry/quality/layer 过滤。
3. **选股 active/reject OB**：`/api/picks` 默认只应展示可交易 `ACTIVE_CANDIDATE`，`/api/picks?include_reject=1` 和 `/api/picks/rejects` 才展示 REJECT。
4. **reversal 专线 OB**：必须独立看，不能和 continuation 默认选股混在一起。

## Pine/LuxAlgo OB数量控制原则

LuxAlgo/Pine 口径的 OB 不是“每次结构 break 都画一个区间”。正确收缩链路：

```text
BOS/CHOCH break 成立
→ break candle 需要足够强 displacement
→ 从 break bar 向后找最近反向 K 作为 OB
→ 去重
→ mitigation/交易层过滤
→ 默认前端只展示可交易 active，不展示 REJECT
```

本次发现的关键缺失是：代码记录了 displacement，但没有把 Pine 参数中的 `OB Displacement Multiplier = 1.5` 当成 OB 生成硬门槛，导致普通结构突破也生成 OB。

## 最小修复模式

目标函数：

```text
/root/.hermes/scripts/v25/smc_core_luxalgo_v34.py
order_blocks_from_structure()
```

在生成 OB 前加 break bar displacement 硬过滤：

```python
break_bar = klines[bi]
break_rng = max(break_bar['h'] - break_bar['l'], 1e-9)
break_disp = break_rng / max(atr[bi], 1e-9)
if break_disp < 1.5:
    continue
```

并写入审计字段，方便前端/回测逐笔查证：

```python
'break_displacement_mult': round(break_disp, 3),
'displacement_pass': break_disp >= 1.5,
'strength': strength,
'min_strength_pass': strength >= 3,
```

## 验证标准

修复不是只看总数下降，必须验证所有入口同步：

```bash
cd /root/.hermes/scripts
python3 -m py_compile smc_unified.py v25/smc_core_luxalgo_v34.py v25/v46_1_layered_3y.py
python3 v25/v46_1_layered_3y.py --rebuild-base
```

然后重启前端 8890，并验证：

```text
/api/summary?ver=V46_1
/api/picks
/api/picks?include_reject=1
/api/picks/rejects
/api/picks/contract
/api/kline_full?symbol=<代表股票>&ver=V46_1
```

必须同时确认：

- `/api/picks` 默认没有 REJECT。
- `/api/picks?include_reject=1` 的 OB 数量大于默认页是正常的，因为它包含审计拒绝项。
- K线图 OB 数量随核心 detector 修复下降。
- 全量回测文件与前端 ACTIVE_VERSION 指向同一版本。

## 关键隐藏坑：ACTIVE_VERSION 优先级

本次还发现前端可能因为 V24 文件存在而优先选择 V24，导致 summary/picks 看起来和 V46.1 回测不一致。

修复原则：V46.1 输出存在时必须优先 V46.1：

```python
ACTIVE_VERSION = ('V46_1' if Path('/root/.hermes/smc_opt_v46_1_layered_3y/v46_1_report.json').exists()
                  else 'V24' if Path('/root/.hermes/smc_opt_v24/v24_trades.json').exists()
                  ...)
```

## 经验数据参考

本次修复前后数量级：

```text
LuxAlgo OB before: 169,440 total / avg 36.45 per symbol
LuxAlgo OB after:   63,965 total / avg 13.76 per symbol
reduction: -62.2%
```

修复后与 SMC2026 `min_strength_pass` 量级接近：

```text
SMC2026 min_strength_pass: 60,072 total / avg 12.92 per symbol
```

代表 K线图 OB-like 标识下降：

```text
600519.SH: 38 → 13
000727.SZ: 34 → 10
000065.SZ: 41 → 12
300750.SZ: 37 → 14
```

## 工作流纪律

当用户指出 OB 数量异常时，按以下顺序执行：

1. 先统计各入口 OB 数量，不要凭肉眼判断。
2. 审计 detector 定义是否符合 Pine/LuxAlgo 参数，尤其是 displacement hard gate。
3. 最小修改核心 detector，而不是前端隐藏。
4. 全量重跑 V46.1。
5. 重启前端并 HTTP 验证 summary/picks/rejects/kline/contract。
6. 报告中明确区分：展示信号、回测交易、active 选股、reject 审计、reversal 专线。

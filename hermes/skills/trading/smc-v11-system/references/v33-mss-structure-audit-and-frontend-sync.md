# V33 MSS结构修复与前端同步经验

## 适用场景

当SMC系统出现以下问题时使用：

- BOS/CHOCH/MSS 信号看起来“有”，但交易胜率低、止损多。
- 全部交易都来自 CHOCH，BOS/MSS语义混杂。
- 普通 CHOCH 被当成可交易 MSS 使用。
- 多周期共振页日线显示 UNKNOWN。
- 前端重跑接口仍硬编码旧版本，如“当前仅允许重跑V31”。

## Pine核对结论

SMC 2026 / LuxAlgo 的结构逻辑本质是：

```pine
close crossover pivotHigh:
    previous trend bearish => CHOCH
    otherwise => BOS

close crossunder pivotLow:
    previous trend bullish => CHOCH
    otherwise => BOS
```

关键含义：

- CHOCH只是趋势方向切换标签，不等于交易入场信号。
- BOS是顺趋势结构突破。
- MSS不是普通CHOCH；可交易 MSS 必须是 CHOCH + liquidity sweep + displacement。
- 若交易全来自普通CHOCH，通常是结构语义错位，而不是SL/TP参数问题。

## V32D问题模式

V32D 62笔交易审计发现：

- source_event=CHOCH: 62/62
- BOS交易: 0/62
- MSS-qualified: 31/62
- 非MSS普通CHOCH: 31/62

根因：引擎把普通 CHOCH 当成 MSS 交易触发器。

第二个问题：zone允许出现在结构事件后最多8根：

```python
z.index <= ev_idx + 8
```

这会让未来形成的OB/FVG解释过去结构，形成后验污染。

## V33修复规则

只修结构语义，不调SL/TP：

```python
if ev.type == 'CHOCH' and not ev.is_mss:
    continue
```

zone近端绑定：

```python
z.index <= ev_idx + 2
```

保留：

- limit retouch入场
- HIGH_VOL过滤
- 原SL/TP参数

不启用：

- zone_width <= 6%：会误杀高盈利交易
- reject_strength >= 0.45：会误杀高盈利弱wick比例但有效的MSS交易

## 验证结果

| 版本 | 交易数 | WR | avg_pnl | total_pnl | SL数 | SL率 |
|---|---:|---:|---:|---:|---:|---:|
| V32D | 62 | 66.1% | 1.23% | 76.37% | 21 | 33.9% |
| V33 | 29 | 75.9% | 2.09% | 60.63% | 7 | 24.1% |

质量变化：

- WR +9.8pp
- avg_pnl +70%
- SL数 21 → 7
- SL率 33.9% → 24.1%
- 所有交易 source_event 从 CHOCH 混杂修正为 MSS

## 前端同步坑

### 日线 UNKNOWN

V32+ picks字段为 `market_state`，旧前端读取 `regime` 会导致 UNKNOWN。

修复：

```python
daily_regime = p.get('market_state') or p.get('regime') or 'UNKNOWN'
daily_ok = daily_regime in ('TREND_UP', 'RANGE')
```

同时确认类型需兼容：

- `BULLISH_REJECTION`
- `PINBAR_RECLAIM`

### 重跑接口硬编码旧版本

不要写死 `ACTIVE_VERSION == 'V31'`。使用版本路由：

```python
engine_map = {
    'V33': ('/root/.hermes/scripts/v25/v33_engine.py', '/root/.hermes/smc_opt_v33', 'v33', 'V33_MSS_RTO'),
    'V32D': ('/root/.hermes/scripts/v25/v32d_engine.py', '/root/.hermes/smc_opt_v32d', 'v32d', 'V32D_FILTERED_RTO'),
    'V32C': ('/root/.hermes/scripts/v25/v32c_engine.py', '/root/.hermes/smc_opt_v32c', 'v32c', 'V32C_LIMIT_RTO'),
}
```

### 重跑OOM/进程被杀

前端服务持有交易/K线缓存时，同步fork全量扫描会造成父进程+子进程内存叠加。重跑前释放缓存：

```python
global _CACHE_MTIME, _TRADES_CACHE, _TRADES_LITE_CACHE, _PICKS_CACHE
_TRADES_CACHE = None
_TRADES_LITE_CACHE = None
_PICKS_CACHE = None
_CACHE_MTIME = 0
import gc
gc.collect()
```

### K线API审计字段

V33前端trade overlay必须返回这些字段，便于验证结构语义：

- `engine`
- `definition_version`
- `source_event`
- `source_event_idx`
- `sweep_idx`
- `zone_idx`

## 验收清单

- `/api/resonance` 中 `dailyRegime` 不为 UNKNOWN。
- `/api/reselect?start=YYYYMMDD` 返回当前ACTIVE_VERSION对应引擎，而不是V31限制。
- `/api/kline_full?...&ver=V33` 返回 `engine=V33_MSS_RTO`、`definition_version=smc_core_v33`、`source_event=MSS`。
- 全量交易中普通CHOCH入场为0。
- SL减少来自结构语义修复，而不是SL/TP参数优化。

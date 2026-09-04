# 超时根因诊断方法论

**发现日期**: 2026-05-19 (V22 Auto-Fix Pipeline)  
**问题**: 超时率 24.2% > 15% 阈值, 按规则 `max_hold_bars+5` 修复无效

## 诊断流程

```
超時率>15% → 先诊断: 是参数超时还是数据截断?
              ├── 检查 entry_idx 分布 → >90%在275-299 → 数据截断
              │   └── 修复: min_remaining_bars 入场过滤器
              └── entry_idx 均匀分布 → 参数超时
                  └── 修复: max_hold_bars+5
```

## 关键判别代码

```python
import json
from collections import Counter

# 1. 检查超时交易的 entry_idx 分布
entry_idxs = [t.get('entry_idx', 0) for t in timeouts]
buckets = Counter()
for e in entry_idxs:
    b = (e // 25) * 25
    buckets[f"{b}-{b+24}"] += 1

# 若 275-299 桶占比 >90% → 数据截断

# 2. 精确判别: hold_bars vs remaining bars
n_limit = 0
param_limit = 0
for t in timeouts:
    hold = t.get('hold_bars', 0)
    entry = t.get('entry_idx', 0)
    remaining = 300 - entry - 1
    if hold >= remaining:
        n_limit += 1
    else:
        param_limit += 1
# 若 n_limit > 90% → 数据截断根因
```

## V22 实测数据

| 指标 | 数值 |
|------|------|
| 超时交易 | 211/871 (24.2%) |
| n-limit (数据截断) | 206/211 (98.1%) |
| param-limit (参数超时) | 4/211 (1.9%) |
| entry_idx 275-299 | 201/211 (95.3%) |
| max_hold_bars+5 修复效果 | 仅1笔变化 (0.5%) |

## 正确修复: min_remaining_bars 过滤器

在引擎入场点添加:
```python
if entry_bar + 25 >= n:  # 至少25bar forward data
    continue
```

### 修复效果

| 指标 | 修复前 | 修复后 | 变化 |
|------|--------|--------|------|
| 交易 | 871 | 305 | -65% |
| 超时率 | 24.2% | 2.0% | -91.7% |
| 均PnL | +9.04% | +11.16% | +23.5% |
| 均赢 | +11.93% | +15.29% | +28.2% |
| Trailing | 52.6% | 62.3% | +18.4pp |
| 入场距zone | 0.84% | 0.64% | -23.8% |

### 副作用

- Regime分布严重偏向HV (95%) — 非HV trades大多晚期入场被过滤
- SL率上升 (11.7%→19.7%, 因分母缩小)

## 根本解决

扩展K线缓存到 400-500 bar 可彻底消除数据截断问题, 同时保留全部交易。

## 引擎文件修改记录

- `/tmp/v22_engine.py` L299: 新增 `if entry_bar + 25 >= n: continue`
- `/tmp/v17_engine.py` L331-351: max_hold_bars +5 (边际保护, 非主要修复)

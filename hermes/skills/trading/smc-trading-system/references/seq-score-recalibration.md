# SEQ_SCORE 自动重校准方法

## 触发条件
每次全量回测后，对比 `v19_engine.py` 中的 `SEQ_SCORE` 字典值与当前实测PnL数据。
若任何已有当前数据的序列的评分偏差 > 2.0，启动重校准。

## 评分公式 (V20.6+, 2026-05-18 重校)

```
score = avgPnL * 0.45 + WR_bonus + min(log2(N) * 0.5, 2.0)
```

- avgPnL: 该序列所有交易的均PnL%（百分比值，如 +15.85 不是 0.1585）
- WR_bonus: WR=100% → +1.0, WR≥90% → +0.5, 否则 0
- N_bonus: min(log2(N) * 0.5, 2.0) — 样本量越大越可信
- 最终值 cap 到 [0.5, 10.0] 区间，保留1位小数

## 执行流程 (cron中使用 execute_code)

```python
import json, re, math
from collections import defaultdict
from pathlib import Path

# 1. 加载回测数据
data_file = Path('/root/.hermes/smc_opt_v19/v19_i1.json')
t = json.loads(data_file.read_text())

# 2. 按序列聚合PnL
seq_stats = defaultdict(lambda: {'pnls': [], 'count': 0})
for x in t:
    s = x.get('ctx_seq', '') or x.get('v19_seq', '')
    if s and x.get('pnl_pct') is not None:
        seq_stats[s]['pnls'].append(x['pnl_pct'])
        seq_stats[s]['count'] += 1

# 3. 计算新评分 (仅N≥2的序列)
def compute_score(avgP, wr, n):
    base = avgP * 0.45
    wr_bonus = 1.0 if wr >= 1.0 else (0.5 if wr >= 0.9 else 0)
    n_bonus = min(math.log2(max(n, 1)) * 0.5, 2.0)
    return round(max(0.5, min(10.0, base + wr_bonus + n_bonus)), 1)

new_scores = {}
for s, d in seq_stats.items():
    if d['count'] >= 2:
        avgP = sum(d['pnls']) / len(d['pnls'])
        wr = sum(1 for p in d['pnls'] if p > 0) / len(d['pnls'])
        new_scores[s] = compute_score(avgP, wr, d['count'])

# 4. 读取引擎现有评分
engine_code = Path('/tmp/v19_engine.py').read_text()
old_entries = re.findall(r"\s+'([^']+)':\s*([\d.]+),", engine_code)
# 构建old_scores dict...

# 5. 计算偏差，若max_dev > 2.0则更新
# 保留历史序列（当前数据中不存在的序列维持原评分，标注 # historical）

# 6. 使用 patch 工具更新 v19_engine.py 的 SEQ_SCORE 块
```

## 关键原则
- **保留历史序列**: 当前回测数据中未出现的序列（如 `TS→OB→CH→FVG→IDM`），维持原评分不变，标注 `# historical (no current data)`
- **按评分降序排列**: 新字典按 score 从高到低排序，当前数据序列在前，历史序列在后
- **注释格式**: `# N=XX WR=XX% avgP=+XX.XX%` 或 `# historical (no current data)`
- **更新注释日期**: 引擎文件顶部注释 `# D1: Signal sequence → V19 empirical PnL (recalibrated YYYY-MM-DD)`

## 历史记录
| 日期 | N | 最大偏差 | 关键变更 |
|------|---|---------|---------|
| 2026-05-18 | 203 | 5.7 | OB→IDM: 2.2→9.6, OB→PB→IDM: 4.4→10.0, OB: 1.0→7.4 |
| 2026-05-17 | 203 | <2.0? | 上次重校? |

## 常见偏差来源
- **样本量变化**: 历史评分基于旧数据集（如 OB→IDM 旧43笔 vs 新94笔）
- **序列演化**: 新信号类型（IF/BRK/OT）加入后，序列组合改变
- **市场状态变化**: 不同时期同一序列表现可能不同

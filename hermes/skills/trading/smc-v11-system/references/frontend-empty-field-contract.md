# SMC 前端字段空值修复与验证

## 触发场景

用户反馈 SMC 前端出现以下问题时使用：

- `/monitor` 选股页缺少或不显示 `选股日期`、`加入日期`。
- 选股页下方引擎列表 `Zone` 为空。
- `/live` 实时页 `成本线`、`波动`、`Zone` 为空。
- 任务重跑后仍反复报“已修复”但页面仍空值。

## 关键判断

不要只看底层 JSON，也不要只看 Python 字段名。前端实际分三层合同：

1. `/api/picks` 使用 snake_case 字段：`pick_date`、`select_date`、`join_date`、`zone_type`、`cost_line`、`volatility_pct`。
2. `/api/live-prices` 给实时页使用 camelCase 字段：`pickDate`、`joinDate`、`entryDate`、`costLine`、`volClass`、`zoneType`、`zoneLow`、`zoneHigh`。
3. `/live` 页面 JS 只读取 camelCase；如果后端只补 snake_case，实时页仍会显示 `-`。

## 修复位置

主要检查 `/root/.hermes/scripts/smc_unified.py`：

- `_normalize_pick_scope()`：统一 `/api/picks` 与选股页字段兜底。
- `build_monitor()`：检查选股页表头与 row 顺序，必须同时包含 `选股日期`、`加入日期`。
- `_api_live_prices()`：监控仓位路径会从 `load_positions()` 读取 `raw_pick`，必须把 `pos` 和 `raw_pick` 合并后补齐实时页 camelCase 输出。
- `build_live()`：确认 JS 读取字段名，不要误以为 snake_case 会自动显示。

## 最小验证脚本

修复后必须验证 API 层没有空值：

```python
import json, urllib.request
from collections import Counter

data = json.loads(urllib.request.urlopen('http://127.0.0.1:8890/api/live-prices', timeout=10).read().decode())
rows = data.get('picks', [])
miss = Counter()
for p in rows:
    for k in ['pickDate','joinDate','entryDate','costLine','volClass','zoneType','zoneLow','zoneHigh']:
        if p.get(k) in (None, '', 0, [], {}):
            miss[k] += 1
print({'n': len(rows), 'missing': dict(miss)})
```

还要浏览器验证：

- `/monitor` 第一张“每日选股 → 实时监控”表有 `选股日期`、`加入日期`。
- `/monitor` 第二张“当前有效选股”表有 `选股日期`、`加入日期`，`Zone` 不是空。
- `/live` 表有 `成本线`、`Zone`、`波动`，且不是 `-`。

## 常见坑

- `v66_picks.json` 底层字段缺失不一定代表前端会空；运行时归一化可能已补齐。结论必须以 API 和页面验证为准。
- 监控仓位来自 `smc_monitor_state` 的 positions；实时页优先使用 `raw_pick` + position 字段，不是直接读取 `/api/picks`。
- 同一问题要同时验证 API 和 DOM。只验证 API 可能漏掉前端字段名不匹配；只看页面可能误判缓存或旧服务。
- 如果用户说“任务继续执行一直出错”，不要复述计划；直接重跑修复链路并给页面级验证结果。

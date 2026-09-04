# V103A 前端生产路由与字段合同验收

## 触发场景

用户要求修复 SMC 前端字段空值，尤其是：
- 选股页新增/修复 `选股日期`、`加入日期`
- 选股页 `engine`、`zone` 为空
- 实时页 `成本线`、`波动`、`zone` 为空
- 新生产版本已生成 JSON，但页面仍显示旧版本或字段为空

## 稳定处理顺序

1. **先确认输出文件不是空源头**
   - 检查版本目录下的 `*_active_picks.json`、`*_candidate_picks.json`、`*_trades.json`、`*_report.json`
   - 确认 active picks 数量、首行字段、report 中 `production_total` / `active_pick_total`

2. **生产路由必须覆盖所有入口**
   - 新增版本目录常量，例如 `V103A_DIR`
   - `_promoted_contract_dir()`：新版本放在最高优先级
   - `_active_pick_mtime()`：加入新版本 active picks mtime，否则缓存不会刷新
   - `_v88_latest_market_date()`：加入新版本 report，否则页面日期可能仍旧
   - `_promoted_trade_file()` / `get_version_trades('V88')`：V88 外壳必须读新版本 trades
   - `_merge_v90_daily_picks()`：新版本 active 存在时不要混入 V90 旧扫描
   - `_merge_v91_shadow_picks()`：优先合并/返回新版本 active picks
   - monitor/live/API 路由：`/api/picks`、`/api/live-prices`、daily monitor、summary、analysis 入口都要同步

3. **重启时必须确认进程加载的是新代码**
   - 比较 `smc_unified.py` 文件 mtime 与 `smc_unified.py` 进程启动时间
   - 如果进程启动时间早于文件修改时间，说明 8890 仍是旧代码，必须 kill 后重新启动
   - 不要用 shell `&` 启动长期服务；用受管后台进程，再做端口/HTTP 健康检查

4. **验收必须 API + 浏览器两层都过**
   - API：`/api/picks` 与 `/api/live-prices` 字段缺失统计必须为 0
   - 页面：`/monitor` 必须显示版本标题、新增日期列、engine、Zone、成本线、波动
   - 页面：`/live` 必须显示选股日期、加入日期、买入日期、成本线、Zone、波动、状态/操作
   - 不要只看 HTML 源码；以浏览器快照或渲染结果为准

## API 字段缺失验收脚本

```python
import json, urllib.request
base = 'http://127.0.0.1:8890'

def fetch(path):
    with urllib.request.urlopen(base + path, timeout=60) as r:
        return json.loads(r.read().decode())

picks = fetch('/api/picks')
live_payload = fetch('/api/live-prices')
live = live_payload.get('picks', []) if isinstance(live_payload, dict) else []
keys = [
    'engine', 'pick_date', 'join_date',
    'zone', 'zone_type', 'zone_low', 'zone_high',
    'cost_line', 'smart_money_cost',
    'volatility_pct', 'volatility',
    'tp1', 'tp2', 'tp3', 'sl', 'rr',
]
for name, rows in [('picks', picks), ('live', live)]:
    miss = {k: sum(1 for r in rows if r.get(k) in (None, '', 0)) for k in keys}
    engines = sorted({str(r.get('engine')) for r in rows})
    print(name, 'rows=', len(rows), 'engines=', engines)
    print('missing=', miss)
```

通过标准：
- `picks` 与 `live` 行数符合当前生产 active picks
- `engine` 为当前生产版本，例如 `V103A_RISK_GATE`
- 上述字段缺失全为 0
- 浏览器 `/monitor` 与 `/live` 中用户点名字段均可见且非空

## 关键坑

- `/api/live-prices` 的实时行在 `payload['picks']`，不是顶层列表。
- 新版本 active picks 存在但 `/api/picks` 返回空，优先检查前端进程是否仍是旧代码，以及 `_merge_v90_daily_picks()` 是否因新版本存在直接返回空但未被后续 shadow 合并覆盖。
- patch fallback 链时不要覆盖旧版本 fallback（例如加入 V103A 后仍要保留 V102/V101/V100 回退）。
- 工具执行完后必须把验证结果写进最终回复；不要在浏览器验证后返回空响应。

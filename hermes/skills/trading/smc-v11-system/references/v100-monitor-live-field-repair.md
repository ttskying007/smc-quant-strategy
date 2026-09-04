# V100 /monitor + /live 字段空值修复与验收

## 触发场景

用户反馈 SMC 前端：
- 选股页面需要显示「选股日期」「加入日期」两列。
- 选股页某些引擎行 `Zone` 为空。
- 实时页 `成本线`、`波动` 为空。
- 任务 ID 无法继续执行或 cron job not found 时，仍要按业务目标直接修复当前 8890 前端，不停在任务 ID 错误。

## 核心根因

V98/V100 结构化引擎的 POI/Zone 信息可能存放在嵌套字段：

```python
production_gate.zone_low
production_gate.zone_high
production_gate.zone_type / poi_type / type
```

旧前端只读 flat 字段：

```python
zone_low / zone_high / dz_low / dz_high
cost_line / smart_money_cost
volatility_pct / risk_pct / v25_sl_pct
```

因此 `/monitor`、`/api/live-prices`、`/live` 会在新引擎数据结构下出现 Zone/成本线/波动空值。

## 修复模式

优先在统一字段合同函数 `_apply_smc_field_contract()` 里补齐，而不是在每个页面重复兜底：

1. 读取 `production_gate` dict。
2. 如果 flat `zone_type` 为空，用 `production_gate.zone_type / poi_type / type` 回填。
3. 如果 flat `zone_low/zone_high` 为空，用 `production_gate.zone_low/zone_high` 或 `low/high` 回填。
4. `smart_money_cost/cost_line` 用 zone 中线或 entry price 回填。
5. `volatility_pct` 用 `v25_atr_pct / atr_pct / risk_pct / sl_initial_pct / v25_sl_pct` 回填。
6. 输出浏览器/API aliases：
   - 日期：`pickDate`, `joinDate`, `selectDate`, `entryDate`, `选股日期`, `加入日期`
   - Zone：`zone`, `zoneType`, `zoneLow`, `zoneHigh`
   - 成本/波动：`costLine`, `cost_line`, `volatilityPct`, `volatility_pct`, `volatility`

## 页面展示要求

### `/monitor`

表头必须包含：

```text
代码 | 引擎 | 选股日期 | 加入日期 | ... | Zone | 成本线 | 波动 | ...
```

行内至少显示：

```text
Zone: DEMAND_OB [9.17~9.23]
成本线: 9.20
波动: 0.65%
```

### `/live`

表头统一使用完整中文字段名，避免用户认为字段缺失：

```text
代码 | 选股日期 | 加入日期 | 买入日期 | ... | 成本线 | Zone | ... | 波动
```

## 验收脚本

修复后必须同时验证 API 和实际页面：

```bash
python3 -m py_compile /root/.hermes/scripts/smc_unified.py

python3 - <<'PY'
import json, urllib.request, re
base='http://127.0.0.1:8890'
for path in ['/api/picks','/api/live-prices','/monitor','/live']:
    data=urllib.request.urlopen(base+path, timeout=30).read().decode('utf-8','ignore')
    print('\nPATH', path, 'bytes', len(data))
    if path.startswith('/api/'):
        j=json.loads(data)
        picks=j.get('picks') if isinstance(j,dict) else j
        required=['pick_date','select_date','join_date','pickDate','joinDate','zone','zoneType','zoneLow','zoneHigh','costLine','cost_line','volatilityPct','volatility_pct']
        bad=[]
        for i,p in enumerate(picks or []):
            miss=[k for k in required if p.get(k) in (None,'',0) and k not in ('zoneLow','zoneHigh')]
            if not (p.get('zoneLow') and p.get('zoneHigh')):
                miss.append('zoneLow/zoneHigh')
            if miss:
                bad.append((i,p.get('symbol'),miss))
        print('count', len(picks or []), 'bad_required', bad[:5])
        if picks:
            p=picks[0]
            print({k:p.get(k) for k in ['symbol','engine','pick_date','select_date','join_date','zone','zoneType','zoneLow','zoneHigh','costLine','volatilityPct']})
    else:
        print('None', data.count('None'), 'NaN', len(re.findall(r'\bNaN\b',data)), 'undefined', data.count('undefined'))
        for needle in ['选股日期','加入日期','成本线','波动','Zone']:
            print(needle, needle in data)
PY
```

Expected:

```text
/api/picks       bad_required []
/api/live-prices bad_required []
/monitor         None 0, NaN 0, required headers present
/live            None 0, NaN 0, required headers present
```

`undefined` can appear as a literal JavaScript guard (`r.pnl_pct === undefined`) and is not automatically a rendered-page failure; inspect context before treating it as data corruption.

## Operational notes

- If a user gives a stale/missing cron task ID, first list jobs if needed, but do not block on the missing ID. Continue from the explicit business requirement and repair the live system.
- Use GitNexus impact before editing `build_monitor`, `build_live`, `_api_live_prices`, or other symbols in `smc_unified.py`; these edits are typically LOW risk but must still be checked.
- Restart 8890 as a tracked background process, then verify readiness via `/api/summary` and browser/API checks.

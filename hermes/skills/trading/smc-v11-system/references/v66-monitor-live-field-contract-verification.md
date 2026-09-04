# V66 选股页/实时页字段合同验收补充

## 触发场景

用户反馈 SMC 前端字段为空或任务重跑反复失败，尤其是：

- 选股页 `/monitor` 缺少或未显示“选股日期”“加入日期”
- 选股页引擎后面的 Zone 为空
- 实时页 `/live` 成本线、波动为空
- 任务 ID 重跑后仍声称修复但前端未验证

## 最小修复/验收路径

1. **先查字段合同入口**：`smc_unified.py` 中 `_apply_smc_field_contract()`、`_normalize_pick_scope()`、`build_monitor()`、`Handler._api_live_prices()`。
2. **不要只看 HTML 表头**：必须同时验证 API 数据和浏览器页面。
3. **接口级零空值验收**：
   - `/api/picks`：统计 `pick_date/select_date`、`join_date`、`zone_type 或 zone_low/zone_high`、`cost_line/smart_money_cost/v25_cost_line`、`volatility_pct/risk_pct/v25_sl_pct/v25_vol_class` 的空值数。
   - `/api/live-prices`：统计 `pickDate/pick_date`、`joinDate/join_date`、`zoneType/zone_type 或 zoneLow/zoneHigh`、`costLine/cost_line`、`volClass/volatility_pct` 的空值数。
4. **浏览器级验收**：打开 `/monitor` 和 `/live`，确认表头与首屏单元格都有实际值。
5. **若数据已正常但用户仍看到空值**：优先重启 8890 服务、清前端缓存或确认用户访问的是同一实例；不要继续改策略引擎。

## 验收脚本片段

```python
import json, urllib.request

def blank(v):
    return v in (None, '', 0, '0', '-')

for path in ['/api/picks', '/api/live-prices']:
    data = json.loads(urllib.request.urlopen('http://127.0.0.1:8890' + path, timeout=20).read().decode())
    rows = data.get('picks', data if isinstance(data, list) else []) if isinstance(data, dict) else data
    print(path, len(rows))
    if path == '/api/picks':
        print('blank pick_date', sum(blank(r.get('pick_date') or r.get('select_date')) for r in rows))
        print('blank join_date', sum(blank(r.get('join_date')) for r in rows))
        print('blank zone', sum(blank(r.get('zone_type')) and not (r.get('zone_low') and r.get('zone_high')) for r in rows))
        print('blank cost', sum(blank(r.get('cost_line') or r.get('smart_money_cost') or r.get('v25_cost_line')) for r in rows))
        print('blank vol', sum(blank(r.get('volatility_pct') or r.get('risk_pct') or r.get('v25_sl_pct') or r.get('v25_vol_class')) for r in rows))
    else:
        print('blank pickDate', sum(blank(r.get('pickDate') or r.get('pick_date')) for r in rows))
        print('blank joinDate', sum(blank(r.get('joinDate') or r.get('join_date')) for r in rows))
        print('blank zone', sum(blank(r.get('zoneType') or r.get('zone_type')) and not (r.get('zoneLow') and r.get('zoneHigh')) for r in rows))
        print('blank cost', sum(blank(r.get('costLine') or r.get('cost_line')) for r in rows))
        print('blank vol', sum(blank(r.get('volClass') or r.get('volatility_pct')) for r in rows))
```

## Related reference

- `references/v66-frontend-live-source-parity.md` — use when API field blanks are already zero but `/monitor`, `/api/picks`, and `/live` still disagree because they read different sources (`v66_picks.json`, `positions.json`, ledger).

## Browser verification fallback

If `browser_vision` fails or produces an oversized screenshot payload, do not stop at API checks. Use `browser_console` to extract table headers and first rows directly from the DOM, for example:

```javascript
Array.from(document.querySelectorAll('table')).map((t,ti)=>({
  ti,
  headers:Array.from(t.querySelectorAll('thead th, tr:first-child th')).map(th=>th.textContent.trim()),
  rows:Array.from(t.querySelectorAll('tbody tr')).slice(0,5).map(tr=>Array.from(tr.cells).map(td=>td.textContent.trim()))
}))
```

For `/monitor`, verify both tables separately:

1. “每日选股 → 实时监控” table: `选股日期` and `加入日期` should be present and populated.
2. “当前有效选股” table: `引擎`, `选股日期`, `加入日期`, `Zone`, `成本线`, `波动` should be present and populated.

For `/live`, verify first-screen rows include non-blank `选股日`, `加入日`, `成本线`, `Zone`, and `波动`. Treat `'-'`, `''`, `0`, `0.00`, and `0.00%` as blank for this task.

## Live page volatility display pitfall

In `/api/live-prices`, both numeric volatility fields and class/state fields may be present:

- Numeric: `volatilityPct`, `volatility_pct`, `volatility`
- Class/state: `volClass`, `vol_class`, `market_state`

For the `/live` table's `波动` column, display numeric percent first and only fall back to class/state when numeric volatility is absent. A previous regression rendered `RECOVERY` / `MIXED` in the 波动 column because the JS used `p.volClass || p.vol_class || volatilityPct`. The durable fix is:

```javascript
let volStr = (p.volatilityPct ? Number(p.volatilityPct).toFixed(2)+'%'
  : (p.volatility_pct ? Number(p.volatility_pct).toFixed(2)+'%'
  : (p.volClass || p.vol_class || '-')));
```

Add/keep a regression test that verifies:

1. `/api/picks` has zero blanks for pick date, join date, zone, cost, numeric volatility.
2. `/api/live-prices` has zero blanks for pick date, join date, zone, cost, numeric volatility.
3. `/monitor` current picks table has `选股日期`, `加入日期`, `Zone`, `成本线`, `波动` populated.
4. `/live` has `选股日`, `加入日`, `成本线`, `Zone`, `波动`, and the rendered 波动 is a numeric percent, not market-state text.

A reusable test from this session was saved as `/root/.hermes/scripts/v25/test_frontend_field_contract_mpkfagiawk77km.py`; future sessions can adapt it for the current active version rather than relying on API-only checks.

## Source-of-truth lesson from repeated task reruns

When a user reports that a prior task ID repeatedly failed, search/read the request dump only to understand the failed scope, then re-run the concrete field-contract verification against the live service. Do not assume the old failure means the frontend is still broken; prove it with API zero-blank counts and DOM/table validation. If the live service already satisfies the contract, report the verified state instead of making unnecessary strategy or engine changes.

Important no-op verification pattern:

- Treat "no code patch needed" as a valid completed repair only after live API + DOM checks both pass.
- `/api/picks` and `/api/live-prices` can both have zero blanks while the page-level issue was stale cache, old instance, or an already-applied previous patch; in that case do not invent another backend/engine change.
- For `/monitor`, validate both tables separately: the upper "每日选股 → 实时监控" table and the lower "当前有效选股" table. A pass on only one table is incomplete.
- On `/live`, `现价` may show `-` during休市 because realtime quotes are not fetched, but that is not a failure if `最后价格`, `行情状态`, `成本线`, `Zone`, and `波动` are populated. Do not confuse market-closed realtime price blanks with the requested cost/volatility blanks.
- In the final response, state clearly whether files were changed or the existing live service was verified as already satisfying the contract; Lei cares about verified outcome, not cosmetic activity.

## Related K-line chart marker contract

- `references/v88-kline-marker-contract.md` — use when `/monitor` and `/live` fields pass but `/kline` loses buy markers, TP/SL lines, or signal sequence labels. It covers V88 default-version drift, `symbol=` URL param handling, active-pick overlays for V90/V91 scanner rows, and ECharts markPoint/markLine verification.

## V88 manual rerun pitfall

If `/api/reselect` returns `当前版本暂不支持重跑，ACTIVE_VERSION=V88`, the failure is usually not the V88 engine itself. Check `smc_unified.py::Handler._api_reselect()`:

1. `engine_map` must include `V88`: `('/root/.hermes/scripts/v25/v88_apply_production_contract.py', '/root/.hermes/smc_opt_v88_production_contract', 'v88', 'V88_PRODUCTION_CONTRACT')`.
2. `_api_reselect` already has a V88 branch later, so a missing `engine_map` entry makes the guard fail before the branch is reached.
3. After fixing, POST `/api/reselect?start=20260101&end=20260612` should return `ok:true`, `engine:V88_PRODUCTION_CONTRACT`, `all_trades:532`, and non-zero `wr`.
4. If `wr` returns `0.0` despite valid V88 PnL, inspect `is_winner()`: modern engines should use numeric `pnl_pct > 0` whenever `pnl_pct` exists, not a hardcoded engine-name allowlist.
5. Restart the actual process bound to 8890; a second background start may fail with `Address already in use` while the old process continues serving stale code.

## Code-safety note

After frontend field-contract changes, at minimum run `python3 -m py_compile /root/.hermes/scripts/smc_unified.py`. If GitNexus `detect-changes` cannot diff because the working directory is not a git repository, do not treat that as a frontend failure; still report the impact-analysis blast radius already collected and the syntax/API/browser validation results. If no file was changed, still run `py_compile` when `smc_unified.py` is the serving file so the final report has a syntax baseline.

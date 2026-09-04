# V66 前端日期、扫描元信息与实时字段同步

适用场景：SMC 选股页或实时页出现字段为空、日期无法判断、早盘推送不是最新扫描结果。

## 典型症状

- 选股页缺少“选股日期 / 加入日期”。
- 页面只显示 Active 数量，无法判断最新行情日是否已扫描。
- Zone/引擎列为空，通常是 watchlist/API 字段 fallback 不完整。
- 实时页 `costLine` 或 `volClass` 为空。
- 早盘推送没有先执行最新 K线刷新、daily scan、ingest。

## 修复顺序

1. 当前选股源必须是最新全市场扫描/watchlist，不能用历史 trades 伪装当前候选。
2. 早盘推送入口先执行：`python3 v25/smc_daily_ops.py run`。
3. 统一从 `/root/.hermes/smc_monitor/ops_latest.json` 暴露扫描元信息：
   - `data_date`
   - `latest_scan_date`
   - `last_scan_at`
   - `scan_returncode`
   - `scan_duration_sec`
   - `kline_ok / kline_failed`
4. `/api/picks` 与选股页字段 fallback：
   - 选股日期：`pick_date → select_date → signal_date → conf_date → entry_date`
   - 加入日期：`join_date → pick_date → select_date → entry_date`
   - Zone：`zone_type → signal_type → entry_type → conf_type`
   - 引擎：生产扫描标识优先，例如 `V66_FULL_MARKET_SCAN`
5. `/api/live-prices` 必须返回并验证：
   - `scanMeta`
   - `lastScanAt`
   - `latestScanDate`
   - `costLine` 不为空
   - `volClass` 不为空
6. 前端状态栏必须展示：`数据日期 | 最后扫描 | 扫描行情日 | 最新有效选股 | Active | RawFile`。
7. 修改后重启 8890，并端到端验证 API、HTML、早盘推送输出一致。

## 快速验证片段

```python
import urllib.request, json
base='http://127.0.0.1:8890'

picks=json.loads(urllib.request.urlopen(base+'/api/picks',timeout=30).read().decode())
arr=picks if isinstance(picks,list) else picks.get('picks',[])
assert arr, 'api/picks empty'
for p in arr:
    assert p.get('pick_date') or p.get('select_date') or p.get('entry_date'), p
    assert p.get('join_date') or p.get('pick_date') or p.get('entry_date'), p
    assert p.get('zone_type') or p.get('signal_type') or p.get('entry_type') or p.get('conf_type'), p

live=json.loads(urllib.request.urlopen(base+'/api/live-prices',timeout=30).read().decode())
assert live.get('scanMeta'), live.keys()
assert live.get('lastScanAt') or live['scanMeta'].get('last_scan_at')
assert live.get('latestScanDate') or live['scanMeta'].get('latest_scan_date')
missing=[(x.get('symbol'),x.get('costLine'),x.get('volClass')) for x in live.get('picks',[]) if not x.get('costLine') or not x.get('volClass')]
assert not missing, missing

html=urllib.request.urlopen(base+'/monitor',timeout=30).read().decode()
assert '最后扫描:' in html and '扫描行情日:' in html
assert '<th>选股日期</th>' in html and '<th>加入日期</th>' in html
```

## 完成标准

- `/api/picks` 有选股日期、加入日期、Zone/引擎。
- `/api/live-prices` 有扫描元信息，且成本线/波动无空值。
- `/monitor` HTML 可直接看出最新扫描是否执行。
- 早盘推送先完成 preflight 再生成报告。
- 新增当日选股必须进入 `NEXT_DAY_PENDING`，不可当天买入，继续遵守 T+1。
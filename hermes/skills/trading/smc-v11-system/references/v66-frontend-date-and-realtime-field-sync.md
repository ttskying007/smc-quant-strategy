# V66 前端日期与实时字段同步验收要点

适用场景：用户反馈 SMC 选股页/实时页字段为空、日期不可判断、历史交易被误当实时候选，或早盘推送没有反映最新扫描。

## 问题形态

- 选股页面缺少“选股日期 / 加入日期”，无法判断候选何时生成、何时进入监控。
- 选股页状态栏只展示数量，不展示 `数据日期 / 最后扫描 / 扫描行情日`，用户无法判断 daily_scan 是否执行过。
- `zone_type` 或页面“引擎/zone”列为空，常见原因是 watchlist/API 字段映射没有从 `signal_type / entry_type / zone_type` 做 fallback。
- 实时页 `costLine`、`volClass` 为空，常见原因是 `/api/live-prices` 只传历史交易字段，未从监控状态、watchlist 或风险字段 fallback。
- 早盘推送直接读旧状态，未先执行 `smc_daily_ops.py run`，导致推送和前端不是最新行情日。

## 修复顺序

1. 先定位当前生产数据源：当前选股必须来自最新全市场扫描/watchlist，不能用历史 trades 伪装候选。
2. 在早盘推送入口加入 preflight：执行 `python3 v25/smc_daily_ops.py run`，完成 K线刷新、daily_scan、ingest 后再生成报告。
3. 从 `/root/.hermes/smc_monitor/ops_latest.json` 读取扫描元信息，统一暴露：
   - `data_date`
   - `latest_scan_date`
   - `last_scan_at`
   - `scan_returncode`
   - `scan_duration_sec`
   - `kline_ok / kline_failed`
4. `/api/picks` 与选股页必须显示：
   - 选股日期：优先 `pick_date`，fallback `select_date / signal_date / conf_date / entry_date`
   - 加入日期：优先 `join_date`，fallback `pick_date / select_date / entry_date`
   - Zone：优先 `zone_type`，fallback `signal_type / entry_type / conf_type`
   - 引擎：优先生产扫描引擎标识，如 `V66_FULL_MARKET_SCAN`
5. `/api/live-prices` 必须补齐并验证：
   - `scanMeta`
   - `lastScanAt`
   - `latestScanDate`
   - `costLine`：从持仓成本、入场价、smart money cost 等字段 fallback，不能空
   - `volClass`：从 volatility/波动分层 fallback；缺失时给出明确默认分类，而不是空字符串
6. 前端状态栏同时显示：`数据日期 | 最后扫描 | 扫描行情日 | 最新有效选股 | Active数量 | RawFile数量`。
7. 重启 `smc_unified.py` 后做端到端验证。

## 验证脚本片段

```python
import urllib.request, json, re
base='http://127.0.0.1:8890'

picks=json.loads(urllib.request.urlopen(base+'/api/picks',timeout=30).read().decode())
arr=picks if isinstance(picks,list) else picks.get('picks',[])
assert arr, 'api/picks empty'
for p in arr:
    assert p.get('pick_date') or p.get('select_date'), p
    assert p.get('join_date') or p.get('entry_date') or p.get('pick_date'), p
    assert p.get('zone_type') or p.get('signal_type') or p.get('entry_type'), p

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

- 不是只改后端数据，也不是只改局部页面；必须验证 `/api/picks`、`/api/live-prices`、monitor HTML、早盘推送输出四者一致。
- 若新增当日选股，状态必须进入 `NEXT_DAY_PENDING`，不可当天买入；T+1 仍是 release gate。
- 报告中要表格化列出选股日期、加入日期、Zone/引擎、成本线、波动字段是否为空。

## Ledger/source-file closure addendum

When the visible pages and `/api/live-prices` look fixed, continue one level deeper before declaring closure:

1. Browser-check both `/monitor` and `/live` with a DOM scan of target columns, not just raw HTML token checks. Snapshot truncation can hide rows; scan all tables for `''`, `-`, `null`, and `undefined` in required columns.
2. Audit the raw monitor files as well as APIs:
   - `/root/.hermes/smc_monitor/positions.json`
   - `/root/.hermes/smc_monitor/trade_ledger.json`
   - `/root/.hermes/smc_monitor/ops_latest.json`
3. Treat `trade_ledger.json` as part of the contract. Historical BUY/SELL ledger rows must not rely only on frontend fallback; backfill or normalize `select_date`, `join_date`, `engine`, `zone_type`, `cost_line`, `smart_money_cost`, `volatility_pct`, `volClass`, and `vol_class`.
4. Before editing high-risk monitor lifecycle functions such as `append_trade_event`, run GitNexus impact. If risk is HIGH, prefer a low-risk read/output normalization in `smc_unified.py` plus one-time historical ledger backfill, unless the task explicitly requires changing the write path.
5. `/api/live-prices` should emit both camelCase and snake_case aliases for frontend contracts, especially `volClass` and `vol_class`, because different surfaces consume different casing.
6. Final proof should report zero missing fields across: monitor page, live DOM, `/api/live-prices.picks`, `/api/live-prices.tradeLedger`, `/api/picks`, and the raw `trade_ledger.json`.

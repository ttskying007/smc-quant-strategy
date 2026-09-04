# V146 V144 dry-run 只读前端预览隔离教训

当把失败/延迟/生命周期审计结果接到 SMC 前端时，必须默认按 shadow-only 只读审计面处理，不能接入生产选股流。

## 安全接入模式

1. 新增独立页面，例如 `/v144-preview`，只 fetch 独立 dry-run API。
2. 独立 API 只读取物理审计 JSON，例如 `/api/v144-dry-run-preview?scope=latest_per_symbol|recent45|all`。
3. 页面和 API 必须显式保留并展示：
   - `shadow_only=true`
   - `tradable=false`
   - `buy_enabled=false`
   - `trade_action=NO_BUY`
4. 不修改、不复用、不覆盖：
   - `/api/picks`
   - `/api/live-prices`
   - `/api/summary`
   - watchlist
   - monitor state
   - morning push
   - 自动买入/加入持仓逻辑

## 字段兼容

生命周期字段可能来自不同实验批次：
- 状态：`v144_status || lifecycle_status || v143_lifecycle_status`
- 原因：`v144_reason || lifecycle_reason || v143_lifecycle_reason || cancel_reason || note`

前端若只读 `v144_status`，旧 dry-run 文件会显示 `-`，这是展示问题，不代表数据为空。

## 验收门禁

上线/重启后必须同时验证：

```bash
python3 -m py_compile /root/.hermes/scripts/smc_unified.py
curl -sS 'http://127.0.0.1:8890/api/v144-dry-run-preview?scope=latest_per_symbol'
curl -sS 'http://127.0.0.1:8890/api/v144-dry-run-preview?scope=recent45'
curl -sS 'http://127.0.0.1:8890/api/v144-dry-run-preview?scope=all'
curl -sS 'http://127.0.0.1:8890/api/picks'
curl -sS 'http://127.0.0.1:8890/api/live-prices'
curl -sS 'http://127.0.0.1:8890/api/summary'
```

检查三种 dry-run scope：
- `bad_buy_like = rows where tradable or buy_enabled or trade_action != NO_BUY` 必须为 0。

检查生产接口：
- `/api/picks` 不应出现 `v144*`/`v143_lifecycle*` 字段污染。
- `/api/live-prices.picks` 不应出现 `v144*`/`v143_lifecycle*` 字段污染。
- 生产接口中 `trade_action=NO_BUY` dry-run 行数应为 0。

## 结论口径

只能说："V144/V143 生命周期审计已接入只读预览页，生产接口未污染。"
不能说："V144已成为生产选股/买入规则。"

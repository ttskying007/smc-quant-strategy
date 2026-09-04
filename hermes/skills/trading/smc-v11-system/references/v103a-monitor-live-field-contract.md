# V103A 选股页/实时页字段合同修复与验收

## 触发场景

用户反馈选股页缺少 `选股日期`、`加入日期`，下方引擎/Zone 为空，实时页 `成本线`、`波动` 为空，或任务重跑后前端字段不同步。

## 修复要点

1. 先定位数据链路，不只看页面：`/api/picks`、`/api/live-prices`、兼容别名 `/api/live_prices` 都要验证。
2. 选股页必须显示并非空：`engine`、`pickDate`、`joinDate`、`zone`/`zoneType`、`costLine`、`volatility`。
3. 实时页必须显示并非空：`pickDate`、`joinDate`、`entryDate`、`costLine`、`zone`/`zoneType`、`volatility`、`status`。
4. 如果新增 `/api/live_prices` 兼容别名，路由 patch 必须保持后续分支完整：不要把 `/trade` 的 `elif` 吞进实时接口分支。正确形态：
   ```python
   elif path in ('/api/live-prices', '/api/live_prices'):
       self._api_live_prices()
   elif path == '/trade':
       self._html(build_trade())
   ```
5. 重启前先 `python3 -m py_compile /root/.hermes/scripts/smc_unified.py`。
6. 启动长驻 8890 服务必须用受控后台进程，不用 `nohup ... &`，避免 Hermes 无法跟踪进程。
7. 验收不能只看 API：必须浏览器实渲染 `/monitor` 和 `/live`，确认表头和单元格实际显示。

## V103A 验收样例

- `/monitor`：标题 `V103A 当前有效选股`；列包含 `选股日期`、`加入日期`、`Zone`、`成本线`、`波动`；示例行 `002461.SZ / V103A_RISK_GATE / 05-27 / 06-04 / DEMAND_OB [9.17~9.23] / 9.20 / 0.65%`。
- `/live`：列包含 `选股日期`、`加入日期`、`买入日期`、`成本线`、`Zone`、`波动`、`持仓状态`；示例行 `05-27 / 06-04 / 06-04 / 9.20 / DEMAND_OB [9.17~9.23] / 0.65% / SL_HIT`。
- `/api/live-prices` 和 `/api/live_prices` 都应返回同一组 picks，关键字段缺失列表应为 `[]`。

## 稳定性报告补充

V103A 任务中额外生成稳定性审计文件：

- `/root/.hermes/smc_opt_v103a_risk_gate/v103a_stability_report.json`
- `/root/.hermes/smc_opt_v103a_risk_gate/v103a_stability_report.md`

报告结论：`risk_pct>=0.7` 是合理的最小入场前门禁；它降低 SL 波峰与 rolling 方差，但不解决 `hold>10` 后段保护不足。
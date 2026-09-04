# V103A 实时接口字段合同与重启验收教训

## 触发场景
选股页/实时页新增或修复字段时，尤其是 `pick_date`/`join_date`/`zone`/`cost_line`/`volatility`/`risk_pct` 同时影响 `/monitor`、`/live`、`/api/picks`、`/api/live-prices`。

## 关键教训
- `/api/picks` 与 `/api/live-prices` 可能不是同一条归一化输出路径；只在通用 `_apply_smc_field_contract()` 补字段，不一定会进入实时接口最终 JSON。
- 实时接口如果手工构造 `result_picks.append({...})`，必须同时补 snake_case 与 camelCase，例如 `risk_pct` 与 `riskPct`。
- 修改后必须确认旧 8890 进程确实已释放；端口仍绑定旧 PID 时，文件已修但页面/API仍返回旧字段。
- 长命令/大脚本可能被工具层吞输出或超时；验收应拆成小步：先 `/api/picks`，再 `/api/live-prices`，再 `/api/live_prices`，最后浏览器页面。

## 最小验收合同
- `/api/picks`: `symbol, engine, pick_date, join_date, entry_date, zone, zone_type, cost_line, volatility, risk_pct` 全部非空。
- `/api/live-prices` 与 `/api/live_prices`: `symbol, engine, pickDate, joinDate, entryDate, zone, zoneType, costLine, volatility, riskPct` 全部非空。
- `/monitor` 必须肉眼/浏览器验证显示“选股日期、加入日期、Zone、成本线、波动”。
- `/live` 必须肉眼/浏览器验证显示“选股日期、加入日期、买入日期、成本线、Zone、波动、持仓状态”。

## 重启验收顺序
1. `python3 -m py_compile /root/.hermes/scripts/smc_unified.py`
2. 用 `ss -ltnp | grep ':8890'` 找 PID，先 `kill`，必要时再 `kill -9`。
3. 用后台进程启动 `python3 smc_unified.py`，不要在前台命令里 shell `&`。
4. 分三次小命令验收三个 API 字段缺失计数。
5. 浏览器打开 `/monitor` 与 `/live` 做最终渲染验收。

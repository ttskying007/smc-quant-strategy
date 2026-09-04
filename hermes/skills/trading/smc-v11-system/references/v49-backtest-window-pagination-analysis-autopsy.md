# V49 回测窗口过滤、分页与分析/复盘口径同步

## 触发场景
用户在前端回测页手工选择时间窗口（例如 `20260101~20260522`），但历史交易详细列表仍出现窗口外交易（如 2023 年），或交易笔数/资金曲线/分析/复盘与窗口不一致。

## 根因
- V49 引擎输出文件可能仍是全量交易 JSON，前端 `/backtest` 如果直接 `reload_trades()` 渲染，会把窗口外交易也显示出来。
- 手工触发回测后如果只 `location.reload()`，会丢失用户输入的 `start/end` 参数，页面回到默认窗口或全量口径。
- 历史交易明细若按 `exit_date` 排序，会让用户以为交易时间错乱；用户要求“历史交易按时间排序”时，应以买入日 `entry_date` 为主排序。
- `/analysis` 和 `/autopsy` 如果继续直接使用全量 `reload_trades()`，会与回测页窗口口径不一致。

## 修复模式
1. 增加统一窗口过滤函数：
   - 输入：`trades, start, end`
   - 口径：按 `entry_date` 落在 `[start,end]` 内过滤。
   - 排序：`entry_date -> exit_date -> symbol`。
2. `/backtest` 接收 URL 参数：
   - `/backtest?start=YYYYMMDD&end=YYYYMMDD`
   - 所有统计卡片、资金曲线、PnL 分布、出场方式、详细列表都只使用过滤后的窗口交易。
   - 页面明确显示“窗口交易”和“全量文件交易”两个口径，避免混淆。
3. 手工触发回测成功后跳转：
   - 不用 `location.reload()`。
   - 用 `location.href='/backtest?start='+start+'&end='+end` 保留窗口。
4. `/analysis` 和 `/autopsy` 同步支持 `start/end`：
   - `/analysis?start=YYYYMMDD&end=YYYYMMDD`
   - `/autopsy?start=YYYYMMDD&end=YYYYMMDD`
   - 分析页定位为“窗口聚合统计模式”。
   - 复盘页定位为“窗口逐笔诊断摘要模式”。
5. 历史交易、K线下方信号列表、高低点列表、交易列表较长时使用前端分页，不要一次性渲染成不可读长表。

## 验证清单
对 `20260101~20260522` 这类窗口至少验证：

```python
rows = json.loads(re.search(r'var BT_ROWS=(.*?);\\nvar btPage', html, re.S).group(1))
assert all('20260101' <= r['entry_date'] <= '20260522' for r in rows)
assert [r['entry_date'] for r in rows] == sorted(r['entry_date'] for r in rows)
assert not any(r['entry_date'].startswith('2023') for r in rows)
```

并检查：
- 回测页显示“窗口交易”，不是含糊的“总交易”。
- 页面说明包含当前窗口、窗口交易数、全量文件交易数。
- `/analysis` 和 `/autopsy` 无 Traceback，且说明当前窗口和模式。
- API 手工回测返回的 `trades` 应为窗口交易数；如引擎仍生成全量文件，返回 `all_trades` 和说明 `note`，不要让用户误以为全量数就是窗口数。

## 合理口径
- 回测页：交易执行结果视图，必须与当前窗口完全一致。
- 分析页：窗口聚合统计，不是逐笔机制审计。
- 复盘页：窗口逐笔诊断摘要，可列最差交易和分桶，但仍不是完整 SMC 链路追踪；若用户要求信号准确性审计，必须继续做逐笔 `signal_date/signal_index/zone/conf/entry/exit/MFE/MAE` 链路验证。

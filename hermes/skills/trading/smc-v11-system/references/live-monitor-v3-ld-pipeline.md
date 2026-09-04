# L→D 实时监控 Pipeline v3 — 关键坑 (2026-05-14)

## 扫描器: scan_LD_signals.py

### 信号日期过滤
- **int日期减法bug**: `int("20260514") - int("20260415") = 99` 非29天!
- **修复**: `datetime.strptime(date, '%Y%m%d')` + `timedelta(days=N)`
- **窗口选择**: 30天→首次run 528个信号全平。3天→35个信号, WR=79.4%

### 信号选择
- 每个股票扫描所有近期序列 (recent_seqs list), 不只最后一个
- 过滤: `bar < n-3` (留至少3根K线做T+1+forward)
- 跳过 >30天老信号

### SL计算
- zone_lower作为基准SL
- Cap: 不超过entry×0.97 (3%最大loss)
- Floor: 不低于entry×0.995 (0.5%最小距离)
- TP: entry×1.03 (固定3%)

### 周线趋势
- weekly_smc_trend() 用CHOCH/BOS方向+最后结构判断
- 仅选 bullish 股票 (做多only)
- 日线合成周线作为fallback

## 监控器: monitor_check.py V3

### 持仓管理
- **Merge逻辑**: 每次运行从LD_picks.json同步新picks
- **去重key**: `symbol|signal_date|chain`
- 保留已有持仓的盈亏记录和status
- 旧版bug: 首次从picks创建后永不更新→新信号不出现

### T+1过滤
- `entry_day == today` → 跳过 (当天不可卖)
- 仅检查 entry_day != today 的持仓

### 价格获取
- Tencent API: `web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,2,qfq`
- format: `[date, open, close, high, low, volume]`
- BJ板块不支持 (920xxx.BJ → cp=0)
- 符号格式: 支持 `_` 和 `.` 分隔 (自动replace)

### 批量限制
- 每run检查500笔 (超时保护)
- Cron: */30 * * * *, no_agent=true

## 实际表现

### 首次全量 (30天窗口, bug版本)
- 528信号 → 484已平 (92%) — 信号太旧
- WR=70.5% — 包含大量历史已决信号

### 修复后 (3天窗口)
- 35信号 → 34已平, 1持仓
- WR=79.4% (27TP/7SL)
- avgTP=+3.01%, avgSL=-2.99%
- 累计PnL=+60.3%

### 回测对比
- 实时WR=79.4% vs 回测bullish WR=84.3% (-4.9pp)
- 差距: 实时只含最近3天(小样本), 回测含全历史
- 趋势正确: 实时也在75-85%区间

## Cron配置
```json
{
  "job_id": "7d268bd6dc08",
  "name": "SMC LD Monitor (bullish+LD)",
  "schedule": "*/30 * * * *",
  "script": "monitor_check.py",
  "no_agent": true
}
```

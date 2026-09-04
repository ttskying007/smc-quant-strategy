# SMC 系统每日全流程健康检查清单

## 适用场景

交易日开盘前后检查 SMC V66 所有 cron 任务、闭环、前端、选股、持仓状态是否完整无误。用户 Lei 要求：数据驱动、无中间汇报、全量验证。

## 检查步骤

### 1. 确认时间与日期

```bash
date '+%Y-%m-%d %H:%M:%S %A %Z'
```

- 确认交易日（周一至周五）和交易时段
- 盘前（<09:30）：检查闭环/早盘推送
- 盘中（09:30-15:00）：检查实时监控
- 盘后（>15:00）：检查收盘处理

### 2. 检查 Hermes Cron 任务

```bash
cat /root/.hermes/cron/jobs.json | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'{j[\"name\"]:40s} last={j[\"last_run_at\"][:19]:>20s} status={j[\"last_status\"]:>8s} next={j[\"next_run_at\"][:19]:>20s}') for j in d['jobs']]"
```

验证每个 SMC 任务的状态为 `ok`：

| 任务名 | 定时 | 检查项 |
|---|---|---|
| SMC Autonomous Closed Loop V65+ | 00:00 | last_status=ok |
| SMC Morning Holdings Picks Push | 08:30 交易日 | last_status=ok |
| daily-multi-source-crawler-v4.5 | 06:00 | last_status=ok |
| Send cto-status-report | 09:00 | last_status=ok |
| clash-subscription-hunter | 06:00 | last_status=ok |

### 3. 检查闭环产物

```bash
cat /root/.hermes/smc_daily_closed_loop/$(date +%Y%m%d)_v66_closed_loop.json
```

验证：
- 8 steps 全部 `returncode: 0`
- `release_gate.pass: true`
- `release_gate.failed_checks: []`
- `t1_audit.violation_count: 0`
- `provenance_audit.pass_count: n_trades`
- `sequence_audit.violation_count: 0`

### 4. 检查 V66 报告

```bash
cat /root/.hermes/smc_opt_v66/v66_report.json
```

关注：
- `metrics.n_trades`（回测总数）
- `metrics.raw_wr`（胜率）
- `metrics.avg_pnl`（平均盈亏）
- `metrics.avg_realized_r`（盈亏比）

### 5. 检查早盘推送报告

```bash
ls -lt /root/.hermes/smc_push_reports/ | head -5
cat /root/.hermes/smc_push_reports/$(date +%Y%m%d)*_morning_push.md | head -20
```

验证：
- 报告已生成（正确日期）
- OPEN 持仓数与 positions.json 一致
- 买入日字段固定取 `created_at`，非 `pick_date`
- 选股已分最新日/历史候选/已持仓/NEXT_DAY_PENDING

### 6. 检查持仓状态

```bash
python3 -c "
import json
p = json.load(open('/root/.hermes/smc_monitor/positions.json'))
for s in ['OPEN','NEXT_DAY_PENDING','CLOSED']:
    print(f'{s}: {sum(1 for x in p if x.get(\"status\")==s)}')
for x in p:
    if x.get('status') in ('OPEN','NEXT_DAY_PENDING'):
        print(f'{x[\"symbol\"]:12s} st={x[\"status\"]:18s} ep={x.get(\"entry_price\",0):>8} sl={x.get(\"sl_price\",0):>8} tp={x.get(\"tp1_price\",0):>8}')
"
```

### 7. 检查 T+1 违规

```bash
cat /root/.hermes/smc_daily_closed_loop/$(date +%Y%m%d)_v66_closed_loop.json |
  python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'step={s[\"cmd\"]:30s} rc={s[\"returncode\"]}') for s in d['steps']]"
```

违规 = 0 为 pass。

### 8. 验证前端 API

```bash
python3 -c "
import urllib.request,json
base='http://127.0.0.1:8890'
live=json.loads(urllib.request.urlopen(base+'/api/live-prices',timeout=15).read().decode())
picks=json.loads(urllib.request.urlopen(base+'/api/picks',timeout=15).read().decode())
summ=json.loads(urllib.request.urlopen(base+'/api/summary',timeout=15).read().decode())
mon=json.loads(urllib.request.urlopen(base+'/api/monitor/state',timeout=15).read().decode())
print(f'live: {live.get(\"total\")} picks: {len(picks)} wr: {summ.get(\"win_rate\")} open: {mon.get(\"summary\",{}).get(\"open\")} pending: {mon.get(\"summary\",{}).get(\"pending\")} closed: {mon.get(\"summary\",{}).get(\"closed\")}')
print(f'error: {live.get(\"error\",\"\")[:80]}')
"
```

### 9. 检查错误日志

```bash
tail -30 /root/.hermes/smc_monitor/errors.log
```

无 error.log 或文件为空为 pass。

### 10. 汇总结论

| 检查项 | 通过条件 |
|---|---|
| 闭环 | 8步全 0 |
| Release Gate | pass=true |
| T+1 违规 | 0 |
| 溯源违规 | 0 |
| 序列违规 | 0 |
| 早盘推送 | 已生成 |
| 今日选股 | 无或符合预期 |
| 前端 | 4 API 正常 |
| 错误日志 | 无错误 |

## 常见问题处理

- **pick_scope 全为 EXPIRED_REVIEW**: 正常，V66 质量门禁严格，无新候选通过过滤
- **每日引擎 09:07 后所有 active 候选过期**: 正常，每日引擎重跑后标记旧候选中为 expired
- **v66_daily_candidates 有 146 条但 /api/picks 为 0**: 候选被 reject，查看 reject_reason 分析
- **早盘报告显示 14 active 但 09:07 后变成 0**: 日盘引擎重跑刷新的正常行为

# V20.2 前端全自动加载架构

## 问题

V20.1之前, `smc_unified.py` 所有数据源在模块顶层一次性加载:

```python
V19_TRADES = load_json(Path('/root/.hermes/smc_opt_v19/v19_i1.json'), [])
V19_PICKS = load_json(Path('/root/.hermes/smc_opt_v19/v19_picks.json'), [])
DEFAULT_TRADES = V19_TRADES
MONITOR = V19_PICKS
```

Cron每日09:00更新`v19_i1.json`和`v19_picks.json`, 但前端进程内存中仍是旧数据。

## 修复: 实时reload函数

```python
def reload_trades():
    """每次请求重新从磁盘加载"""
    t = load_json(Path('/root/.hermes/smc_opt_v19/v19_i1.json'), None)
    if t: return t
    t = load_json(Path('/root/.hermes/smc_opt_v18/v18_autopsy.json'), None)
    if t: return t
    return load_json(Path('/root/.hermes/smc_opt_v17/v17_complete.json'), [])

def reload_picks():
    p = load_json(Path('/root/.hermes/smc_opt_v19/v19_picks.json'), None)
    if p: return p
    ...
```

每个build函数顶部调用:
```python
def build_dashboard():
    trades = reload_trades()   # ← 每次HTTP请求重新读盘
    picks = reload_picks()
    ...
```

## 涉及的页面 (7/8个)

| 页面 | 修复前数据源 | 修复后 | 风险 |
|------|-------------|--------|------|
| `/` | DEFAULT_TRADES(模块级) | reload_trades() | 低 |
| `/monitor` | MONITOR(模块级) | reload_picks() | 低 |
| `/backtest` | DEFAULT_TRADES(模块级) | reload_trades() | 低 |
| `/analysis` | **V9静态JSON** | reload_trades()+动态生成 | 中(重写) |
| `/compare` | **V16固定文件** | reload_trades()+动态统计 | 中(重写) |
| `/autopsy` | V18_TRADES(模块级) | reload_trades()+v19/v18自适应 | 中(重写) |
| `/kline` | 始终实时读盘 | 不变 | 无 |
| `/docs` | 静态 | 不变 | 无 |

## /analysis 重写要点

废弃 `AI_REPORT = OUT_V9 / 'analysis' / 'ai_analysis_report.json'`, 改为:

1. **上下文影响力**: 从`trades`实时计算`ctx_score`分布 → WR/均盈/强度
2. **市场状态×SL/TP**: 从`trades`按`regime`分组统计, 显示每状态参数
3. **自动诊断**: 基于出口分布(SL%/timeout%)+状态PnL+上下文分层+IDM确认率自动生成4类建议

## /compare 重写要点

废弃 V16 的 `comparison.json` + `pick_crossref.json`, 改为:

1. **引擎版本对比**: 从`trades`按`engine`分组统计
2. **个股交叉统计**: 从`trades`按`symbol`聚合 → A/B/C/D评级排序

## /autopsy 适配要点

V19字段名为`v19_overall/v19_seq/v19_efficiency/v19_exit_qual/v19_risk/v19_verdict`
V18字段名为`autopsy_overall/autopsy_signal/autopsy_entry/autopsy_sltp/autopsy_combo/autopsy_verdict`

统一逻辑: 检测`has_v19`/`has_autopsy` → 设置`vkey='v19_'`或`'autopsy_'` → 所有后续代码使用`f'{vkey}field'`访问

## 注意事项

- `reload_trades()`和`reload_picks()`在服务器启动时调用一次(填充DEFAULT_TRADES/MONITOR初始值)
- 每个HTTP请求再次调用, 读盘延迟可忽略(JSON文件<300KB)
- 无需重启前端, cron更新JSON后页面即时刷新

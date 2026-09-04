# V20.1 选股SL/TP集成

## 更新路径

1. `/tmp/gen_v19_picks.py` — 从V19回测交易中提取SL/TP参数写入picks
2. `/root/.hermes/scripts/smc_unified.py` — 前端monitor页增加状态/SL/TP三列

## picks新增字段

| 字段 | 来源 | 示例 |
|------|------|------|
| `regime` | 回测交易 | HIGH_VOLATILITY |
| `sl_initial_pct` | tp_tiers字符串 | 6.5 |
| `tp_tiers` | tp_tiers字符串解析 | [4.0, 8.0, 13.0, 24.0] |
| `atr_pct` | 回测交易 | 4.58 |
| `hold_bars` | 回测交易 | 29 |
| `exit_reason` | 回测交易 | trailing |
| `pnl_pct` | 回测交易 | 7.21 |

## 按市场状态分布的SL/TP (V20.1参数)

| 状态 | 数量 | SL | TP tiers |
|------|------|-----|----------|
| HIGH_VOLATILITY | 191只 | 6.5% | [4,8,13,24] |
| STRONG_TREND_UP | 25只 | 2.6% | [3,6,10,14,26] |
| RANGING | 40只 | 3.2% | [2,3,5,8] |
| WEAK_TREND_UP | 9只 | 3.9% | [2,4,6,10,19] |

## 前端monitor页新增列

表头: 代码|引擎|S|质量|回撤|现价|Zone|**状态**|**SL**|**TP**|序列

- **状态**: 市场状态简写 (HV=🔴, RG=🟡, ST=🟢, WT=🔵)
- **SL**: `SL=6.5%` 红色
- **TP**: `TP:4,8,13` 绿色小字，显示前3档

## Picks生成脚本 (gen_v19_picks.py)

```python
tp_str = t.get('tp_tiers', '')
tp_list = [float(x.replace('%','')) for x in tp_str.split(',')] if tp_str else []

picks.append({
    'regime': t.get('regime', '?'),
    'sl_initial_pct': t.get('sl_initial', 0),
    'tp_tiers': tp_list,
    'atr_pct': t.get('atr_pct', 0),
    'hold_bars': t.get('hold_bars', 0),
    'exit_reason': t.get('exit_reason', '?'),
    'pnl_pct': t.get('pnl_pct', 0),
})
```

## Cron集成

gen_v19_picks.py在cron步骤3中执行（engine后、前端重启前）。
脚本路径: `/tmp/gen_v19_picks.py`
输出: `/root/.hermes/smc_opt_v19/v19_picks.json` (265只)

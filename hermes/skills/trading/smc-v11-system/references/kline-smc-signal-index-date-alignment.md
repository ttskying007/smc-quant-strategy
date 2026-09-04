# K线图 SMC 信号偏移：快照 idx 与当前K线坐标不一致

## 触发场景
用户指出 K线图表中的 SMC 信号仍然偏移。上一轮只修了 V66 最新候选高亮层（zone_bar / entry_idx），但通用 SMC 信号层（signals_list：BOS/CHOCH/FVG/OB/SWING/LV 等）仍偏移。

## 根因
V50/V66 信号快照中同时存在：

| 字段 | 含义 |
|---|---|
| `date` | 信号真实发生日期，应作为图表锚点 |
| `idx` | 旧快照生成时的确认窗口/截面坐标，不一定等于当前 K线数组索引 |

错误模式：前端/接口直接用 `idx` 画图，导致信号整体右移或错位。例：`301047.SZ` 修复前 `FVG_Bear date=20230425 idx=6`，但当前 K线数组 `idx=6` 对应 `20230505`。

## 修复原则
不要继续相信快照里的裸 `idx`。K线接口应先基于当前返回的 `klines` 建立日期索引：

```python
chart_date_idx = {}
for i, k in enumerate(klines):
    d = str(k.get('date', ''))[:10]
    if d:
        chart_date_idx[d] = i
        chart_date_idx[d.replace('-', '')] = i
```

然后对所有绘图相关坐标按日期重新映射：

- `signal.date -> signal.idx`
- `pivot_date -> pivot_idx / line_start_idx`
- `line_end_date or signal.date -> line_end_idx`
- `wave_turn_date -> wave_turn_idx`
- `created_by_event_date -> created_by_event_index`

保留 `_raw_idx` / `_raw_pivot_idx` 等用于审计旧快照坐标。若信号有日期但日期不在当前 K线窗口内，必须过滤，不要用旧 `idx` 硬画。

## 验证标准
对多个样本逐信号验证：

```python
for s in signals_list:
    idx = s['idx']
    assert s['date'][:8] == klines[idx]['date'][:8]
```

至少验证：

- `301047.SZ`
- `001330.SZ`
- `301525.SZ`

通过标准：`bad=0`。同时浏览器打开 `/kline?s=301047.SZ`，信号表 Bar 与 API 日期一致。

## 关键教训
K线偏移要分层排查：

1. 最新候选高亮层：`zone_bar / entry_idx`。
2. 通用 SMC 信号层：`signals_list[].idx`。
3. 结构线层：`pivot_idx / line_start_idx / line_end_idx`。
4. 交易标记层：`_chart_idx / _exit_idx`。

不能只修一个层就报告“偏移已解决”。用户会通过视觉和表格快速发现剩余层的错位。
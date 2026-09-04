# K线 SMC 信号坐标对齐：date 优先于旧 idx

## 适用场景
K线图中 BOS/CHOCH/FVG/OB/SWING/LiquidityVoid 等 SMC 信号整体偏移；尤其是信号表 Bar、图上标记、真实 K线日期三者不一致。

## 核心规则
信号快照中的 `idx` 不是永远可信。若快照来自旧窗口、确认窗口、截断数组或不同缓存长度，`idx` 可能只是生成时坐标。绘图必须以当前 K线数组为准。

优先级：

1. `date` / `pivot_date` / `line_end_date` 等真实日期。
2. 当前接口返回的 `klines[].date`。
3. 由日期建立 `date -> current_bar_index` 映射。
4. 只有缺少日期时才回退旧 `idx`。

## 分层排查清单
不能只修候选高亮就宣称偏移解决。至少检查四层：

| 层 | 字段 |
|---|---|
| 最新候选高亮 | `zone_bar`, `entry_idx` |
| 通用SMC信号 | `signals_list[].idx`, `signals_list[].date` |
| 结构线/摆动点 | `pivot_idx`, `line_start_idx`, `line_end_idx`, `wave_turn_idx` |
| 交易标记 | `_chart_idx`, `_exit_idx`, `entry_date`, `exit_date` |

## 推荐实现

```python
chart_date_idx = {}
for i, k in enumerate(klines):
    d = str(k.get('date', ''))[:10]
    if d:
        chart_date_idx[d] = i
        chart_date_idx[d.replace('-', '')] = i

for s in signals_list:
    if s.get('date') in chart_date_idx:
        s['_raw_idx'] = s.get('idx')
        s['idx'] = chart_date_idx[s['date']]
```

同理映射：

- `pivot_date -> pivot_idx / line_start_idx`
- `line_end_date or date -> line_end_idx`
- `wave_turn_date -> wave_turn_idx`
- `created_by_event_date -> created_by_event_index`

若信号有日期但当前 K线窗口不存在该日期，过滤该信号，禁止使用旧 `idx` 绘制。

## 验证标准

```python
bad = []
for s in signals_list:
    idx = s.get('idx')
    if not (0 <= idx < len(klines)):
        bad.append(s)
    elif str(s.get('date', ''))[:8] and str(s['date'])[:8] != klines[idx]['date'][:8]:
        bad.append(s)
assert not bad
```

建议至少验证三只样本，并打开浏览器查看信号表 Bar 与图上位置一致。
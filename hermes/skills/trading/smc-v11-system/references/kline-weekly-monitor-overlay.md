# K线周线 + 监控持仓 BUY/SL/TP Overlay

## 场景

K线页面需要同时显示：
1. 当前监控持仓的 BUY 点位 + SL/TP 线
2. 历史回测买卖点 (BT1/BT2/...)
3. 周线图也要正确显示买入/卖出/SL/TP

## 实现要点

### 周线模式路由

- 选择器加入 `<option value="weekly">周线</option>`
- `_api_kline_full()` 中 `tf == 'weekly'` 分支读取 `*_weekly_200.json` 或 `*_weekly_300.json` 文件
- 缓存在 `kline_cache/` 目录下，文件格式 `{symbol}_weekly_{bars}.json`，bar 字段含 `t`（非 `date`）

### 日期 → 周线 bar 索引映射

日线交易日期（如 20260605）无法直接匹配周线 bar date（周线是用周末日期），需要 fallback：

```python
date_keys_sorted = []
for i, k in enumerate(klines):
    d_norm = str(k.get('date', k.get('t', '')))[:10].replace('-', '')
    date_map[d_norm] = i
    date_keys_sorted.append((d_norm, i))

def _chart_idx_for_date(v):
    d = _date_key(v)
    if d in date_map:
        return date_map[d]
    # 日线交易日期找不到精确周线bar → 找第一个 >= 买入日的周线bar
    for dk, ii in date_keys_sorted:
        if dk >= d:
            return ii
    return date_keys_sorted[-1][1]
```

### 监控持仓 overlay

在获取 `trades`（从回测数据）后，再从 `load_positions()` 获取当前监控持仓：

```python
if load_positions:
    for pos in load_positions():
        if pos.get('symbol') != symbol or pos.get('status') not in ('OPEN', 'NEXT_DAY_PENDING'):
            continue
        raw = pos.get('raw_pick') or {}
        # append to trades list with entry_detail='durable_monitor_position'
        # 字段映射：entry_price/sl_price/tp1_price 从 pos 或 raw 提取
        # combo: 'BUY' 或 'PENDING'
        trades.append({...})
```

### 历史回测 vs 监控持仓区分

- 历史回测 trade: `_combo` = `BT1`, `BT2`, ...（原有的 combo 字段）
- 监控持仓: `_combo` = `BUY` (OPEN) 或 `PENDING` (NEXT_DAY_PENDING)
- 通过 `entry_detail == 'durable_monitor_position'` 标识
- 历史回测 SL/TP 字段可能缺失：V66 结构出场不保存 TP 字段 → 对盈利交易用 `exit_price` 作为目标线

### SL/TP 绘制

- SL 线: `markLine` 在 `sl` 价格，label = `SL xx.xx`
- TP 线: `markLine` 在 `tp_price` 价格，label = `TP xx.xx`
- 对 `OPEN` 持仓（无 exit_price），跳过 SELL 标记绘制（之前会报错）
- 用 `if(xp>0){...}` 保护退出点渲染

### 全量 trades 不截断

- 取消 `trades[:100]` 限制，改为 `for ti, t in enumerate(trades):`
- 避免当前股票有多笔回测交易时只显示前 100 笔

## 常见问题

- **周线图 BUY点不显示**: 日期映射用精确匹配失败 → 必须用 fallback（找第一个 >= 买入日的周线 bar）
- **监控持仓 exit_idx 越界**: OPEN 持仓没有 exit_date，`_exit_idx` 设为 `ci+1` 或 `dates.length-1`
- **历史回测 SELL 标记显示乱**: 对 monitor trade 不绘制 SELL 点

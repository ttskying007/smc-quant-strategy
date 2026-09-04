# 实时页最后价格 Fallback 与价格状态

## 场景

实时监控页面（`/live`）需要：
1. 休市时、停牌时显示最后一笔可追溯价格（不能只显示"休市"）
2. 明确区分价格来源：实时 / 休市最后K线 / 停牌最后K线 / 无价格
3. 新增 "最后价格" 和 "行情状态" 两列

## 实现

### 后端：`_api_live_prices()` 中的 Cache Fallback

当 `market_open = False` 或腾讯实时行情无数据时，从 K线 cache 读取最后一根 bar 的收盘价：

```python
def _last_cached_bar(symbol):
    sym_file = symbol.replace('.SH','_SH').replace('.SZ','_SZ').replace('.BJ','_BJ')
    for fp in (CACHE / f'{sym_file}_daily_750.json', CACHE / f'{sym_file}_daily_300.json'):
        if fp.exists():
            try:
                arr = json.loads(fp.read_text())
                if arr:
                    b = arr[-1]
                    price = float(b.get('c') or 0)
                    high = float(b.get('h') or 0)
                    low = float(b.get('l') or 0)
                    prev = float(arr[-2].get('c') or 0) if len(arr) > 1 else 0
                    d = str(b.get('t') or b.get('date') or '')[:8]
                    return {'price': price, 'high': high, 'low': low, 'prev_close': prev, 'date': d}
            except Exception:
                pass
    return {'price': 0, 'high': 0, 'low': 0, 'prev_close': 0, 'date': ''}
```

### 价格状态判定

```python
live_price = float(quote.get('price') or 0)
last_bar = _last_cached_bar(sym)
last_price = live_price or float(last_bar.get('price') or 0)
current_price = last_price

if live_price > 0:
    price_status = '实时'
elif not market_open and last_price > 0:
    price_status = '休市-最后K线'
elif market_open and last_price > 0:
    price_status = '停牌/无实时-最后K线'
else:
    price_status = '无价格'
```

### API 返回新增字段

每条持仓记录增加：
- `lastPrice` — 最终可追溯价格（实时 or K线缓存）
- `livePrice` — 仅实时行情来源
- `priceStatus` — 行情状态标签
- `lastPriceDate` — 最后价格对应日期

### 前端表格新增列

```javascript
// 新增列：
<th>最后价格</th>
<th>行情状态</th>
<th>持仓状态</th>

// 行渲染：
let lastStr = p.lastPrice > 0 ?
    p.lastPrice.toFixed(2) + (p.lastPriceDate ? '<br><small>'+p.lastPriceDate+'</small>' : '') :
    '<span style="color:#8b949e">-</span>';
let priceStatus = p.priceStatus || (marketOpen ? '无实时' : '休市');
```

### 状态排序

新的状态排序权重（`status_order`）：
```python
status_order = {
    'SL_HIT': 0, 'TP_HIT': 1, 'T1_LOCKED': 2,
    'SL_CLOSE': 3, 'TP_CLOSE': 4, 'HOLDING': 5,
    'NO_LIVE_LAST_PRICE': 6,    # 新增：有最后价格但无实时
    'NEXT_DAY_PENDING': 7,
    'NO_DATA': 8
}
```

### 前端状态标签

- `NO_LIVE_LAST_PRICE` → 显示 "最后价" 标签
- `NO_DATA` → 显示 "无价格" 标签（之前是 "休市"）
- `NEXT_DAY_PENDING` → 显示 "待次日买入" 标签

## 常见问题

- **全部显示 NO_DATA**: 检查 kline_cache 目录是否存在对应 `*_daily_*.json` 文件
- **休市时现价列为 "-"**: 确认 `_last_cached_bar()` 能否找到缓存文件
- **停牌股价格不变**: 正常，最后K线价格是停牌前最后一笔

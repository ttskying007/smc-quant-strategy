# V22监控页数据陷阱 (2026-05-18)

## 1. K线日期字段名陷阱

**症状**: /monitor 显示"无近期选股(45天内)"，但picks JSON中778只有数据

**根因链**:
1. K线缓存文件使用 `t` 作为日期字段 (`{'t': '20260514', 'o':..., 'c':...}`)
2. V22引擎中 `dates = [b.get('date', f'bar{i}') ...]` — 用 `date` 查找返回空 → 全部fallback到 `bar{i}`
3. 生成的trades和picks中 `entry_date` 全为空/非日期字符串
4. `/api/live-prices` 过滤: `str(p.get('entry_date', '')) >= cutoff` — 空字符串 `< cutoff` → 全部过滤

**修复**:
```python
# v22_engine.py 第117行
dates = [b.get('t', b.get('date', f'bar{i}')) for i, b in enumerate(daily)]
```

## 2. Pick字段映射缺失

**症状**: /monitor 页显示778行但 S/回撤/现价/Zone/SL/TP列全为0/空/? 

**根因**: V22 trades字段名与 monitor页面期望字段名不同:
- trades: `entry_price`, `cost_line`, `conf_type`, `entry_to_zone_pct`, `sl_distance`
- monitor期望: `price`, `dz_low`, `dz_high`, `entry_quality`, `retrace_pct`, `sl_initial_pct`

**修复**: 生成picks时显式映射14个前端期望字段:
```python
pick = {
    'symbol': sym,
    'engine': 'V22',
    'score': int(ctx_score / 2),      # 映射ctx_score→score
    'entry_quality': quality,          # 映射conf_type→中文标签
    'retrace_pct': entry_to_zone,      # 映射entry_to_zone_pct
    'price': entry_price,              # 映射entry_price→price
    'dz_low': cost_line,               # 映射cost_line→dz_low
    'dz_high': max(zone_high, dz_low*1.03),  # 估算zone_high
    'sl_initial_pct': sl_distance,     # 映射sl_distance
    'tp_tiers': [],
    'regime': regime,
    'seq': ctx_seq,
    'detail': f"{zone_type}→{ctx_seq}→{conf_type}",
    'entry_date': entry_date,          # ⚠️ 必须! 45天过滤关键
}
```

## 3. Symbol格式映射

trades中symbol格式: `000027.SZ` (点分隔)
Kline文件命名: `000027_SZ_daily_300.json` (下划线)
映射: `f.stem.split('_')` → `f"{parts[0]}.{parts[1]}"`

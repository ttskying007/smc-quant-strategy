# SMC 前端数据同步模式

## 常见不同步根因

### 1. 版本选择器缺失当前版本
**症状**: K线页面默认显示旧版本（V19/V25），但数据是V27
**根因**: `<select id="ver">` 中未添加V27选项
**修复**: 将V27添加为首个 `<option>`，并设为 `selected`

### 2. 默认ver参数不匹配
**症状**: API返回的version字段与前端显示不一致
**根因**: `qs.get('ver', ['V11'])[0]` — 默认版本是V11
**修复**: 改为 `qs.get('ver', ['V27'])[0]`

### 3. 日期格式不匹配
**症状**: K线有交易数据但trades_count=0
**根因**: K线日期 "2025-02-17" vs 交易日期 "20250704"
**修复**: 双索引date_map，同时存储原始和去横线格式
```python
d_norm = d_raw.replace('-', '')
date_map[d_raw] = i
if d_norm != d_raw:
    date_map[d_norm] = i
```

### 4. Monitor 日期过滤陷阱
**症状**: Monitor页面显示为空或不一致
**根因**: V27 picks的 entry_date 是历史日期（如20250704），日期过滤 cutoff=今天 导致全部过滤
**修复**: 使用state字段过滤
```python
if any(p.get('state') for p in picks):
    active = [p for p in picks if p.get('state') == 'ACTIVE']
    picks = active + historical[:100]
```

### 5. ver_map全量加载
**症状**: K-line API每次请求加载所有版本数据
**根因**: ver_map构建时对每个版本调用 _vdata() 加载完整JSON
**修复**: 仅V27使用内存缓存，其他版本lazyload
```python
ver_map = {'V27': get_trades_cached(lite=True), 'V25': None, ...}
if ver != 'V27' and ver in _ver_paths:
    ver_map[ver] = _vdata(_ver_paths[ver])
```

## 回测页面优化

- 交易表格限制500行（47k行HTML→500行）
- 累计PnL曲线采样到2000点（47k点→2k点）
- 移除 `<meta http-equiv="refresh">` 自动刷新
- 移除重型 trade_by_sym 字典构建

## 变量未定义陷阱

Python变量在条件分支中赋值，但在分支外使用时可能未定义：
```python
# BUG: zb只在else分支中定义
if cond:
    ...
else:
    zb = ...
if zb >= 0:  # UnboundLocalError!
    ...

# FIX: 提前初始化
zb = -1
if cond:
    ...
else:
    zb = ...
if zb >= 0:
    ...
```

## JavaScript 全局变量引用

ECharts在Python f-string中渲染时，注意花括号转义：
```python
# 错误：Python f-string会把 {b} 当变量
f"formatter: '{{b}}: {{c}}'"

# 正确：双花括号转义
f"formatter: '{{{{b}}}}: {{{{c}}}}'"
```

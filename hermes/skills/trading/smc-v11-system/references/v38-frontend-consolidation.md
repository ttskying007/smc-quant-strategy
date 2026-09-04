# 前端统一服务器 — 架构与经验

## 动机

原4个前端页面各占独立端口:
- 8897: V1 K线查看器 (smc_trade_viewer.py, 337行)
- 8896: V2 13信号查看器 (smc_trade_viewer_v2.py, 1206行)
- 8894: V3 统计面板 (smc_dashboard_v3.py, 193行)
- 8895: V4 分析面板 (smc_dashboard_v4.py, 465行)

问题: 占用4个端口, 4个Python进程, 用户需要记住不同URL。

## 统一方案

`smc_unified.py` (776行) = 原2201行合并:
- 单进程, 单端口(8890)
- URL路由: /(主页), /v1, /v2, /v3, /v4
- 导航栏: 页面顶部切换
- 数据源: 同时加载V28(用于v1/v2实时K线)和V38.4(用于v3/v4统计)

## 架构

```
smc_unified.py
├── 数据加载 (V28 + V38.4)
├── NAV (共享导航栏HTML)
├── build_v1(symbol) → K线+出入点
├── build_v2(symbol) → 13信号K线查看器 + 60min API
├── build_v2_60min(symbol) → 60min信号检测API
├── build_v3() → 统计面板
├── build_v4() → 分析面板
└── Handler(BaseHTTPRequestHandler)
    ├── / → 主页
    ├── /v1 → K线查看器
    ├── /v2 → 信号查看器
    ├── /api/signals_60min → 60min JSON API
    ├── /v3 → 统计面板
    ├── /v4 → 分析面板
    └── /echarts.min.js → 本地ECharts
```

## 关键编程陷阱

### 1. f-string中ECharts formatter冲突

```python
# BUG: {b}和{c}被Python f-string解析
f'formatter:"{b}: {c}"'  # → NameError: name 'b' is not defined

# FIX: 双花括号
f'formatter:"{{b}}: {{c}}"'
```

### 2. f-string不支持for循环

```python
# BUG: 在f-string中直接使用三元字符串拼接
f'{"".join(f\'<span>{s}</span>\' for s in list)}'

# FIX: 预构建
rows = ''.join(f'<span>{s}</span>' for s in list)
f'{rows}'
```

### 3. 复杂JSON构建避免f-string嵌套

对于需要多次`json.dumps()`的复杂数据, 预构建Python变量:
```python
dates_j = json.dumps(dates)
ohlcv_j = json.dumps(ohlcv_data)
mark_areas_j = json.dumps(mark_areas)
return f'var dates={dates_j};var ohlcvData={ohlcv_j};...'
```

### 4. 共享CSS/JS资源

ECharts本地serve: `/tmp/echarts.min.js`, 所有页面共用:
```python
if parsed.path == '/echarts.min.js':
    self.send_response(200)
    self.send_header('Content-type', 'application/javascript')
    self.end_headers()
    self.wfile.write(open('/tmp/echarts.min.js','rb').read())
```

### 5. 导航栏穿透

每个页面函数独立返回完整HTML, 共享NAV常量:
```python
NAV = """<div class="nav">...</div>"""
def build_v3():
    return NAV + rest_of_html
```

## 旧文件清理

合并后旧文件保留作为参考:
- smc_trade_viewer.py (V1)
- smc_trade_viewer_v2.py (V2)
- smc_dashboard_v3.py (V3)
- smc_dashboard_v4.py (V4)

如需恢复独立运行: 直接执行旧文件即可(各自独立端口)。

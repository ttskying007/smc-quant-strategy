# Hubble API — 关键端点速查

基址: `http://43.167.234.49:3101`
认证: Headers `{"X-API-Key": "123456", "Content-Type": "application/json"}`
完整API: `/openapi.json` 返回243个端点

## A股数据

### K线
```
GET /api/v2/cnstock/stocks?symbol={code}&interval={daily|weekly|monthly}&count={N}
```
返回 `{data: [{time, open, high, low, close, volume}]}` — **newest-first**，需要反转

### 全量股票列表
```
GET /api/v2/cnstock/symbols?limit=6000
```
返回所有A股代码(5400+)

### 实时证券行情
```
GET /api/v2/cnstock/securities?symbols=600519.SH,000858.SZ
```
返回最新报价

### 选股筛选
```
POST /api/v2/stock/cnstock/screener
Body: {conditions: [...], page: 1, page_size: 50}
```
按条件筛选A股

## 基金/ETF

```
GET /api/v2/fund/etf-basic?page=1&page_size=500
```
ETF基本信息列表。注意字段名可能需要查看openapi.json确认。

## 指数

```
GET /api/v2/cnstock/index/basic
```
指数基本信息

## 技术指标

```
POST /api/v2/indicators/batch
Body: {symbol: "600519.SH", indicators: ["RSI", "MACD", "BOLL", "MA"], params: {...}}
```
批量计算技术指标

## 港股/美股/加密货币

- `GET /api/v2/hkstock/...` — 港股端点
- `GET /api/v2/usstock/...` — 美股端点  
- `GET /api/v2/crypto/...` — 加密货币端点

## 已知陷阱

1. **V2 K线返回 newest-first**: 必须反转成 oldest-first 再传信号检测引擎
2. **股票数量限制**: `/api/v2/cnstock/securities` 单次最多约50只，批量扫描需分批
3. **symbol格式**: A股=`600519.SH`, 科创板=`688001.SH`, 创业板=`300750.SZ`, 港股=`00700.HK`, 美股=`AAPL.US`
4. **全市场扫描性能**: 5400只全扫需分页循环，建议限 `limit_stocks=50` 做快速扫描
5. **openapi.json**: 返回243个端点，含部分未公开/实验性端点 — 优先使用V2路径
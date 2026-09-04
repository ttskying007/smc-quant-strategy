# V2.0 Multi-TF Data Sources & API Pitfalls

## API Sources

### 周线 (Weekly)
| Source | URL | Status |
|--------|-----|--------|
| East Money | `push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.600519&klt=102&lmt=200` | ⚠️ 限流严重, ~25%成功率 |
| Sina | `money.finance.sina.com.cn/...getKLineData?symbol=sh600519&scale=week` | ❌ 格式不稳定 |
| Tencent fqkline | `web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,week,,200` | 未验证 |

East Money format: `secid = prefix.code` where prefix=1(SH), 0(SZ), 0(BJ)
Response: `{data: {klines: ["date,open,close,high,low,vol,amt", ...]}}`
Rate limit solution: batch with delays, retry on 502

### 60min
| Source | URL | Status |
|--------|-----|--------|
| Tencent | `ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh600519,m60,,200` | ✅ 稳定 |

Format: `{data: {sh600519: {m60: [[date,open,close,high,low,vol,...],...]}}}`
15线程并行 ~90s for 4551 stocks
Cache: `/root/.hermes/kline_cache/{code}_{market}_60min_500.json`

### 日线
| Source | URL | Status |
|--------|-----|--------|
| Tencent | `ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh600519,m30,,300` | ✅ |
| Hubble | `43.167.234.49:3101/api/cn/kline?code=sh600519&freq=D&key=...` | ❌ Key expired |

### 股票列表
| Source | URL | Status |
|--------|-----|--------|
| East Money | `push2.eastmoney.com/api/qt/clist/get?pn=1&pz=6000&fs=m:0+t:6...` | ⚠️ 分页/格式不稳定 |

## Key Learnings

1. **周线用API不用合成**: 日历周OHLC重采样在数学上等价，但用户明确要求API数据。东方财富klt=102是最可行方案。
2. **日线合成周线失真**: 5-bar chunk ≠ calendar week。牛市时neutral从57%降至真实API的12%。
3. **502限流**: 东方财富易限流，不可并行大量请求。需分批+延迟。
4. **4800→5400的差距**: 约600只缺失日线，分布在所有代码段。批量盲扫可行但慢。

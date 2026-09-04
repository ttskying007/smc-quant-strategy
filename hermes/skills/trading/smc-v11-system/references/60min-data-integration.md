# 60分钟数据集成 (2026-05-09)

## 数据源测试结果

测试A股60分钟K线数据可用性。所有测试使用curl + Python, 部分需要GFW代理(http://127.0.0.1:7890)。

### 腾讯财经 — 可用

URL: `https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={prefix}{code},m60,,200`

代码映射:
- 000001.SZ -> sz000001
- 600000.SH -> sh600000
- 830001.BJ -> sm830001

返回格式(JSON):
```json
{
  "data": {
    "sz000001": {
      "m60": [
        ["202602241030", 11.20, 11.25, 11.48, 11.18, 12345678, {}, 0.45],
        ...
      ]
    }
  }
}
```

每个bar: [timestamp(YMDHMS), open, close, high, low, volume, {}, change_pct]

特点:
- 200 bars = ~50个交易日(08:00-15:00每60min)
- A股交易时间: 09:30-11:30, 13:00-15:00 = 每天4根60min K线
- 200 bars / 4 = 50天
- 需要 curl -L (跟随302 redirect)
- HTTP 200, 不需要代理

### 新浪财经 — 已失效

之前可用的 `money.finance.sina.com.cn/quotes_service/api_json_v2.php/CN_MarketData.getKLineData?symbol=sh000001&scale=60&ma=no&datalen=200`
在后续测试中返回404。可能已迁移或需要不同URL格式。

### 东方财富 — 被墙

push2.eastmoney.com 和 push2his.eastmoney.com 被GFW屏蔽(HTTP 000), 即使通过代理也连接失败。

### 网易 — Bad Gateway

quotes.money.163.com 和 img1.money.126.net 返回HTTP 502。

### 雪球 — IP黑名单

stock.xueqiu.com 返回HTTP 403, 即使通过代理(代理IP也被拉黑了)。

## klines_60min.py 用法

```python
from v11.klines_60min import fetch_60min_kline, get_60min_kline

# 直接获取+自动缓存(推荐)
bars = get_60min_kline('000001.SZ')
# 返回: [{'date':'2026-02-24 10:30:00', 'o':11.20, 'h':11.48, 'l':11.18, 'c':11.25, 'v':12345678, 't':202602241030}]

# 强制刷新缓存
bars = fetch_60min_kline('000001.SZ')
```

## 60min信号检测

```python
from v11.signals_v11 import detect_all_signals_v11
from v11.klines_60min import get_60min_kline

bars = get_60min_kline('000001.SZ')
ohlcv = [{'o':b['o'],'h':b['h'],'l':b['l'],'c':b['c'],'v':b.get('v',0),'date':b.get('date','')} for b in bars]
sigs = detect_all_signals_v11(ohlcv)
print(f'60min: {sigs["stats"]["total"]} signals, {len(sigs["fvg"])} FVG, {len(sigs["sweep"])} Sweep')
```

## 缓存

目录: /root/.hermes/kline_cache_60min/
格式: {symbol_code}_60min_200.json
示例: 000001_SZ_60min_200.json

## 已知限制

1. 只能获取200根K线(~50交易日), 无法获取更长的历史(腾讯API限制)
2. 没有批量接口, 需要逐只股票请求
3. 速率限制: 每0.5s一次, 全量4800约需40分钟
4. 数据精确到日而非stock代码校验, 不存在的股票返回空数据而非错误

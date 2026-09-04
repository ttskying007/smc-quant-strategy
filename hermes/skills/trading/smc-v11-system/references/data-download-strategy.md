# 数据下载策略 (2026-05-14)

## 周线数据

| 源 | 状态 | 覆盖 | 方法 |
|---|------|------|------|
| Hubble API | ✅ 可用 | ~3600只 | `curl -H 'X-API-Key:123456' /api/v2/cnstock/stocks?symbol=X&interval=weekly&limit=200` |
| 腾讯 | ✅ 可用 | ~4800只 | `curl -sSL 'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz000001,week,,,200,qfq'` (-L跟随重定向必须) |
| 东方财富 | ❌ SSL失败 | - | `push2his.eastmoney.com` — Python urllib和curl均SSL error |
| 新浪 | ❌ | - | API返回Input error |
| 网易 | ❌ 超时 | - | 被墙 |

下载脚本: `download_weekly_v3.py` — subprocess+curl, 8并发
关键: 腾讯必须用`-L`跟随302重定向, Python urllib不可用, 必须subprocess+curl

## 60min数据

| 源 | 状态 | 覆盖 | 方法 |
|---|------|------|------|
| 腾讯ifzq | ✅ | 4551只 | `http://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sz000001,m60,,200` |
| 其他 | ❌ | - | BJ股不支持 |

## 日线数据

已全量缓存于 `kline_cache/*_daily_300.json` (4836只)

## 周线合成fallback

当真实周线不可用时, 从日线5根合1周:
```python
def daily_to_weekly(daily):
    for i in range(0, len(daily), 5):
        chunk = daily[i:i+5]
        weekly.append({'o':chunk[0]['o'], 'h':max(b['h'] for b in chunk),
                       'l':min(b['l'] for b in chunk), 'c':chunk[-1]['c']})
```

# 数据刷新工作流 (2026-05-14)

## 日线数据

源: 腾讯ifzq公开API (无需Key)
URL: http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz000001,day,,,300,qfq
关键: curl -L 跟随重定向, Python urllib不可靠

缓存: /root/.hermes/kline_cache/{symbol}_daily_300.json
格式: qfqday数组 [date, open, close, high, low, volume]

当前: 4905/5529 (缺624只BJ/SZ新股)

## 60min数据

源: 腾讯ifzq
URL: http://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sz000001,m60,,200
缓存: /root/.hermes/kline_cache/{symbol}_60min_500.json (4551只)

## 下载方法

用subprocess+curl替代Python urllib:
```python
import subprocess
cmd = ['curl', '-sSL', '--max-time', '15', url]
resp = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
data = json.loads(resp.stdout)
```

原因: Python urllib对东方财富(SSL error)和腾讯(302 redirect)不可靠。

## 并发

today_refresh_pick.py: 20线程并发下载日线+扫描信号
股票列表从kline_cache文件名反向提取, 无需维护独立列表

## 不可用源

- 东方财富: HTTPS SSL问题
- 新浪: 404/格式复杂
- 网易: 502
- Hubble API: Key=123456可用但可能超时, 腾讯优先

## 补全缺失股票

目标: 5529只全市场
缺失: /tmp/missing_stocks.txt
补全: 腾讯API 20并发, 每只curl一次

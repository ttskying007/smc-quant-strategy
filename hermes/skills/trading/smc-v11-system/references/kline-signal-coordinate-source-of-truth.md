# K线 SMC 信号偏移：坐标/价格同源门禁

## 触发场景
用户反馈 K线图上的 SMC 标记横向或纵向偏移，尤其表现为：
- FVG/OB/BOS/CHOCH 标记大面积悬浮在蜡烛上方或远离对应K线；
- `date -> bar` 重映射后偏移更严重；
- 页面信号数量异常偏多，例如 V66 页面显示 379 signals，而当前K线现场计算只有约 195 signals。

## 关键教训
不要只修 `idx` 或 `date` 映射。K线图标记必须同时满足三同源：
1. **K线数据源同源**：信号必须由当前页面加载的 `klines` 数组生成；
2. **横轴坐标同源**：`idx/bar/date` 必须映射到当前 `klines[idx].date`；
3. **纵轴价格同源**：`price/upper/lower/zone_high/zone_low` 必须落在当前K线价格体系附近。

只做 `signal.date -> current bar index` 可能会把旧快照的错误放大：如果旧快照的价格来自另一套复权/缓存/截断窗口，即使日期对齐，标记仍会在价格轴上严重漂移。

## 诊断步骤
对用户指出的股票先跑单股审计，不要直接改前端：

```python
import json, pathlib, sys
sys.path.insert(0, '/root/.hermes/scripts')
import smc_unified as su

sym = '300910.SZ'
ks = json.loads(pathlib.Path(f'/root/.hermes/kline_cache/{sym.replace(".", "_")}_daily_750.json').read_text())
old = su.load_v50_signal_snapshot(sym)
print('klines', len(ks), ks[0]['t'], ks[-1]['t'], 'snapshot signals', len(old))
for s in old[:20]:
    idx = s.get('idx')
    print(s.get('type'), 'rawidx', idx, 'sdate', s.get('date'),
          'chartdate_raw', ks[idx]['t'] if isinstance(idx, int) and idx < len(ks) else None,
          'price', s.get('price'))
```

判断标准：
- 如果 `s.date` 和 `ks[s.idx].t` 不一致，存在横轴旧坐标问题；
- 如果 `s.price` 明显不在 `ks[idx].l ~ ks[idx].h` 附近，存在纵轴价格体系问题；
- 如果两者同时存在，不能继续用旧快照修补。

## 正确修复策略
优先保证 K线页画的是当前K线现场计算结果，而不是旧版本快照：

- V50 这类明确设计为“信号快照同源”的版本可以继续用对应快照；
- V66/V65 等生产版本如果旧快照来自 `smc_opt_v50_signal/v50_signal_snapshot.json`，不要直接拿来画图；
- 对生产版本，应用当前 `data/klines` 调 `smc_core_pine_like.detect_all_signals_pine_like()`，再按版本需要用 LuxAlgo 结构层覆盖/补齐；
- 前端只是渲染最终 API 的 `signals_list`，不要在 JS 里二次猜测旧坐标。

## 验证门禁
修复后必须验证横轴与纵轴：

```python
import urllib.request, json
base='http://127.0.0.1:8890'
sym='300910.SZ'
d=json.loads(urllib.request.urlopen(
    base+f'/api/kline_full?symbol={sym}&tf=daily&ver=V66', timeout=100
).read())

bad=[]
for s in d['signals_list']:
    idx=s.get('idx')
    if not isinstance(idx,int) or idx<0 or idx>=len(d['klines']):
        bad.append(('bad_idx', s)); continue
    k=d['klines'][idx]
    if str(s.get('date',''))[:8] and str(s.get('date',''))[:8] != str(k['date']).replace('-','')[:8]:
        bad.append(('date_mismatch', s.get('type'), idx, s.get('date'), k['date']))
    price=float(s.get('price') or 0)
    if price and (price > k['h']*1.35 or price < k['l']*0.65):
        bad.append(('price_extreme', s.get('type'), idx, s.get('date'), price, k['l'], k['h']))

print('bars', d.get('count'), 'signals', d.get('signal_count'), 'bad', len(bad), bad[:10])
```

必须做到：
- `bad_idx == 0`；
- `date_mismatch == 0`（除非信号有明确 pivot/confirm 双日期语义，需分别字段验证）；
- `price_extreme == 0`；
- 浏览器实际页面的信号数量与 API 返回一致，且不再显示旧快照异常数量。

## 报告要求
用户已经明确指出“偏移越来越厉害”时，回复必须承认上一轮修复层级错误，直接给出：
- 错误层级：只修了 `date/index`，没检查价格/快照同源；
- 真根因：旧快照与当前K线不同源；
- 修复：生产版本改用当前K线现场计算/同源信号；
- 验证：给出单股的 bars/signals/bad 数和关键样本表。

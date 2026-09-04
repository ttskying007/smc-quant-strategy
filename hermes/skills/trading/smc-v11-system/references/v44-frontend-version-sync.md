# V44 前端版本绑定与全量展示同步教训

## 触发场景
用户看到前端胜率只有 50%，但后端 V44/R1 验收结果明显不一致。此类问题不要先怀疑交易逻辑，必须先审计前端实际绑定的数据版本。

## 关键诊断顺序
1. 打开前端页面，确认 `<title>`、导航品牌、首页统计是否显示目标版本。
2. 搜索 `smc_unified.py` 中的 `ACTIVE_VERSION`、`ACTIVE_TRADE_FILE`、`ACTIVE_PICK_FILE`、`reload_metrics()`。
3. 检查版本优先级是否被旧文件抢占：例如 `v24_trades.json` 存在时优先命中 V24，导致页面展示旧胜率。
4. 检查页面静态文案是否残留旧版本号：`SMC V24`、`V24选股`、`V24 回测概览`、`V31 引擎总览` 等。静态文案会误导用户判断当前版本。
5. 逐页验证 `/`、`/backtest`、`/monitor`、`/analysis`、`/autopsy`，不要只验证首页。

## 最小修复模式
- 只改前端绑定和展示层，不动交易引擎。
- `ACTIVE_VERSION` 应优先识别当前正式全量文件（V44 为 `/root/.hermes/smc_opt_v44/v44_full.json`）。
- `ACTIVE_TRADE_FILE` 对 V44 指向 `v44_full.json`。
- `_refresh_cache()` 对 V44 必须从 dict 结构中取 `all_trades`，不能把整个 dict 当 trades list。
- `reload_metrics()` 对 V44 从 `v44_full.json['summary']` 读全量指标。
- 页面标题、导航、卡片标题使用 `{ACTIVE_VERSION}`，不要硬编码 `V24/V31`。

## V44 `v44_full.json` 数据契约坑
`v44_full.json` 结构是：

```json
{
  "summary": {...},
  "stocks": [{"symbol": "000001.SZ", "n_trades": 43, ...}],
  "all_trades": [...]
}
```

`all_trades` 可能缺少前端回测页需要的字段，尤其：
- `symbol`
- `entry_date`
- `exit_date`
- `exit_reason`
- `market_state`
- `entry_mode`

`v44_full_scan.py` 的写入契约是按股票顺序执行：

```python
all_trades.extend(result['trades'])
stock_results.append({'symbol': sym, **p})
```

因此可按 `stocks[].n_trades` 顺序为 `all_trades` 回填 `symbol`。这是前端兼容修复，不代表交易逻辑变化。

## 验证脚本片段
```python
from urllib.request import urlopen
import re
for path in ['/', '/backtest', '/monitor', '/analysis', '/autopsy']:
    html = urlopen('http://127.0.0.1:8890' + path, timeout=60).read().decode('utf-8','ignore')
    stale = bool(re.search(r'SMC V24|V24选股|V24 回测概览|V24 高质量选股|V31 引擎总览|V31实测|V31 逐笔交易复盘诊断', html))
    assert not stale, path
    assert 'SMC V44' in html or 'V44' in html, path
```

## 用户工作流要求
这类全量审计任务不要每一步停下来问用户确认。有明显下一步时，直接继续：定位 → 最小补丁 → 重启 → 多页验证 → 回报最终结果。

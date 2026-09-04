# Frontend Common Pitfalls

## f-string curly brace escape

When HTML content is inside a Python f-string (common in `build_*()` functions), **all curly braces that are NOT Python expressions MUST be escaped by doubling**.

```python
# WRONG — {date, o, h, l, c} inside f-string is parsed as Python set literal
return f"""<pre>- klines: [{date, o, h, l, c}, ...]</pre>"""
# → NameError: name 'date' is not defined

# RIGHT — escape with double braces
return f"""<pre>- klines: [{{date, o, h, l, c}}, ...]</pre>"""
```

## Variable name mixup

Multiple `build_*()` functions historically mixed `v12`/`v13`/`trades` variable names:

```python
# WRONG — v13 loaded but iterates v12
def build_backtest():
    v13 = DEFAULT_TRADES
    pnls = [t['pnl_pct'] for t in v12]  # NameError if v12 not defined in scope

# RIGHT — consistent naming
def build_backtest():
    trades = DEFAULT_TRADES
    pnls = [t['pnl_pct'] for t in trades]
```

**Pattern**: always use `trades` for the currently loaded dataset.

## Startup print crash

`__main__` block's print statements referencing old variable names that were renamed during refactoring cause NameError on startup:

```python
# CRASH — V15_PICKS was renamed but print wasn't updated
print(f"  Picks: {len(V15_PICKS) if V15_PICKS else 0} stocks")  # NameError!
```
**Fix**: Use dynamic variables (MONITOR, DEFAULT_TRADES) in startup prints, not hardcoded version-specific names.

## replace_all=true trap

When replacing a string that is a substring of another string, `replace_all=true` corrupts the longer match:

```python
# Before: "SMC V16 ... SMC V16.2"
patch(old="SMC V16", new="SMC V16.2", replace_all=True)
# After: "SMC V16.2 ... SMC V16.2.2"  ← double-replaced!
```
**Avoid**: Search first to count matches. When one string is a prefix of another, do targeted single-match replacements.

## __pycache__ staleness

After modifying Python files, purge bytecode before restart:
```bash
find /root/.hermes/scripts/__pycache__ -delete 2>/dev/null
```
**Symptom**: code fix applied but error persists → stale .pyc.

## Missing imports

`build_*()` functions using `Counter`/`defaultdict` must import them locally:
```python
def build_backtest():
    from collections import Counter
    ...
```

## Engine auto-detection

Don't hardcode engine names. Auto-detect:
```python
engines = list(set(t.get('engine', '?') for t in trades))
```

## Monitor page dynamic engine display

Use picks data to dynamically compute engine distribution:
```python
eng_stats = {}
for p in picks:
    eng = p.get('engine', 'Other')
    eng_stats[eng] = eng_stats.get(eng, 0) + 1
```

## Version selector in K-line page

Keep `<select id="ver">` current with the latest engine as first option:
```html
<select id="ver">
  <option value="V16.2">V16.2 高级SMC</option>
  <option value="V16.1">V16.1 多周期</option>
  ...
</select>
```

## Branding consistency

All 6 pages (dashboard/backtest/monitor/analysis/docs/kline) must show the same version in nav brand. Use `replace_all=true` on `🚀 SMC Vxx` patterns — but ensure the target string is unique enough not to overlap (see replace_all trap above).

## pnl_pct format

V11+ engine stores `pnl_pct` as percentage (11.31 = 11.31%). Frontend display should NOT multiply by 100 again. avg_pnl = sum/n (not sum/n*100).

## K-line版本映射缺失陷阱 (2026-05-18修复)

`_api_kline_full` handler中 `trade_map` 仅覆盖V13-V16，V17/V18/V19/V12缺失。用户在前端版本下拉选V19时回退到V13数据。

**症状**: 选V19但K线图交易数为0（热门股无V13交易），与回测页数据不一致。

**修复**: 补全ver_map到全部版本(V19→V12):
```python
ver_map = {
    'V19': V19_TRADES, 'V18': V18_TRADES, 'V17': V17_TRADES,
    'V16.2': V16_2_TRADES, 'V16.1': V16_1_TRADES,
    'V16': V16_TRADES, 'V15': V15_TRADES, 'V13': V13_TRADES,
    'V12': V12_TRADES
}
```

**预防**: 每次新增版本引擎时同步更新3处：(1)模块顶部全局加载 (2)`reload_trades()` (3)`_api_kline_full`的ver_map。

## K-line信号高亮与实际交易脱节陷阱 (2026-05-18修复)

旧逻辑：找"最近未击穿OB"→搜索周围信号→标记。完全不参考实际交易记录——标记的是任意OB，不是该股票真实交易的信号位置。用户反馈"看着离当前比较远"。

**新逻辑**: 从交易记录读`signal_date`/`entry_date`→映射到K线bar→标红色方框:
```python
stock_trades = [t for t in ver_map[ver] if t['symbol'] == symbol]
for ti, t in enumerate(stock_trades[:20]):
    sig_date = (t.get('signal_date') or t.get('entry_date'))[:10]
    bi = bar_idx[sig_date]
    highlight.append({'bar': bi, 'num': ti+1, 'type': f'T{ti+1}:{sl}'})
```

## V19字段名不兼容陷阱 (2026-05-18修复)

V19回测数据字段名与旧版本不同，前端代码需兼容:
- `signal_date` → 用 `entry_date` (V19无此字段)
- `signal_type` → 从 `ctx_seq` 取首元素 (`OB→BRK→IDM` → `OB`)
- `pnl_pct`已是百分比(7.20非0.072)，不要×100

**症状**: highlight为空，交易信号栏空白。

## Monitor序列日期缺失 (2026-05-18修复)

选股页面序列列仅显示"OB→IDM"无时间。用户问"每个时间都是什么时候"。

**修复**: 交叉引用V19_TRADES获取entry_date，格式化为"OB→IDM (12-17)":
```python
trade_by_sym = {t['symbol']: t for t in (V19_TRADES or [])}
ed = str(t.get('entry_date', ''))[:8]
date_str = f"{ed[4:6]}-{ed[6:8]}" if len(ed) == 8 else ed
seq_dated = f"{seq} ({date_str})"
```
仪表盘选股Top15和/monitor选股页均需更新。

## K-line Highlight 两层架构 (2026-05-18升级)

旧版本仅标记V19交易entry_date，用户认为zone位置太远。升级为两层:
1. **Z:SEQ** — zone_bar位置(来自V19_TRADES交叉引用)
2. **近期信号** — 最后50bar的OB/CH/LIQ/FVG/PB等(来自detect_sigs实时检测)

详见: `references/kline-highlight-v19.md`

## Auto-refresh meta tag模式 (2026-05-18)

对非AJAX页面可直接在`<head>`加meta refresh:
```html
<meta http-equiv="refresh" content="120">
```
Dashboard/Backtest/Monitor/Analysis/Compare/Autopsy 6页采用此方案。注意: Live/Trade已有AJAX，Kline用户触发，Docs静态 — 不加。

## tp_tiers跨版本格式不兼容 ⚠️ (2026-05-18 fix)

不同引擎版本对`tp_tiers`字段使用不同的数据格式：
- V21及更早: `["6.0", "12.0", "18.0"]` — 百分比数值列表
- V23/V24: `"BOS_level:9.4(9.3%)"` 或 `"FVG_resist:6.92(1.8%),swing_high:7.43(9.3%)"` — 描述性字符串

**症状**: `_api_live_prices()` 调用 `float(tp_tiers[0])` → 字符串"BOS_level:..."取第0个字符`'B'` → `ValueError: could not convert string to float: 'B'` → http.server静默断开连接(exit 52, empty reply)。

**修复**: 对`tp_tiers`做类型判断，字符串用正则提取`(...%)`中的百分比:
```python
tp_pct = 0
if tp_tiers:
    if isinstance(tp_tiers, str):
        import re
        m = re.search(r'\(([\d.]+)%\)', tp_tiers)
        if m: tp_pct = float(m.group(1))
    elif isinstance(tp_tiers, list) and len(tp_tiers) > 0:
        tp_pct = float(tp_tiers[0])
tp_price = entry_price * (1 + tp_pct / 100) if entry_price and tp_pct else 0
```

## 条件块内变量在块外引用导致UnboundLocalError ⚠️ (2026-05-18 fix)

`build_autopsy()`中`vkey`在`if has_autopsy or has_v19:`块内赋值，但在HTML模板f-string中引用，当两个条件都为False时`vkey`未定义:

```python
if has_autopsy or has_v19:
    vkey = 'v19_' if has_v19 else 'autopsy_'
    ...
else:
    verdicts = Counter()
    avg_scores = {}
    # ❌ vkey 未赋值!
    ...
return f"""...{avg_scores.get(f'{vkey}overall', '?')}/10..."""  # UnboundLocalError!
```

**修复**: 在`else`分支也赋值`vkey = ''`，确保所有代码路径都定义该变量。

**症状**: http.server返回空响应(exit 52)，`strace`显示收到请求后直接`shutdown(SHUT_WR)`无任何数据发送。

## http.server静默失败调试 ⚠️

Python的`http.server`在handler抛出未捕获异常时可能静默关闭连接，不发送任何HTTP响应（不返回500），`curl`收到`exit 52 (Empty reply from server)`:

```bash
# 调试方法: 用 -u (unbuffered) + tee 捕获stderr
cd /root/.hermes/scripts && python3 -u smc_unified.py 2>&1 | tee /tmp/smc_debug.log

# 然后另一个终端发请求
curl http://localhost:8890/api/live-prices

# 检查日志中的Traceback
tail -30 /tmp/smc_debug.log
```

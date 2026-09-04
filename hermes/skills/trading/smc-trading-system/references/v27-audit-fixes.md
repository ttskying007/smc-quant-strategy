# V27 审计修复记录 (2026-05-19)

## 发现的7个架构/实现级问题及修复

### 1. BPR锚定bug — find_zone_for_event 永远匹配不到BPR

**根因**: `find_zone_for_event()` 仅匹配 `anchor_event_idx == event_idx`，但BPR zone由opposing FVG overlap生成，没有 `anchor_event_idx` 字段（BPR不绑定单一结构事件）。

**症状**: BPR信号在smc_core_v27中大量生成(1,995,942个/全量)，但交易中BPR zone数量为0。

**修复**:
```python
# 在 find_zone_for_event 中增加 proximity fallback:
elif ae == -1 and zone_type == 'BPR':
    zi = z.get('index', -1)
    if zi >= 0 and zi <= event_idx + 5:
        dist = abs(zi - event_idx)
        if dist < best_dist and dist <= 30:
            best = z
            best_dist = dist
```

**修复后**: BPR=11,573笔(24.4%)，与OB(60%)和OTE(15%)形成三级zone体系。

### 2. BPR区间过窄 — 微FVG重叠产生无效zone

**根因**: 两个FVG重叠可能仅0.14%宽度，无法作为有效交易zone。

**修复**: 在 `build_bullish_setups()` 中增加最小宽度过滤:
```python
if zone_type == 'BPR' and zh > 0 and zl > 0:
    bpr_width = (zh - zl) / zl * 100
    if bpr_width < 0.3:
        continue
```

### 3. 入场位置过松 — 55%入场在zone上方

**根因**: retrace检测 `cl_in_zone = zl * 0.97 <= cl <= zh * 1.03` 允许收盘在zone_high以上3%仍算"回撤"。入场gap过滤 `entry_price > zh * 1.03` 过宽。

**修复**:
- retrace: `zl * 0.98 <= cl <= zh * 1.005` 
- entry gap: `entry_price > zh * 1.015` → 拒绝
- 效果: WR从94.7%(旧缓存)降至57.4%(新扫描)，更真实

### 4. 前端字段兼容性 — KeyError: 'won'

**根因**: V27交易使用 `pnl_pct > 0` 判断盈亏，无 `won` 字段。Dashboard/build_backtest等页面用 `t['won']` 硬括号访问导致崩溃。

**修复**: 全部改为 `.get('pnl_pct',0) > 0` 判断，所有trade字段访问改为 `.get()` 模式:
```python
# ❌ won = sum(1 for t in trades if t['won'])
# ✅ won = sum(1 for t in trades if t.get('pnl_pct', 0) > 0)
```

### 5. K线图信号源不同步 — 仍用V22检测器

**根因**: `_api_kline_full` import `from v11.signals_v22 import detect_all_signals_v22`，K线marker来自V22，而交易数据来自V27。用户肉眼验证时信号位置不一致。

**修复**: 当 `ver='V27'` 时从预生成的 `v27_recent_signals.json` (294MB, 4,649只股票) 加载V27 signal markers，不再实时运行V22检测器。

### 6. 294MB JSON缓存 — 每次请求hang

**根因**: `v27_recent_signals.json` 294MB，每请求加载会导致前端假死(连接接受但不响应)。

**修复**: 添加模块级懒加载缓存:
```python
_V27_RECENT_CACHE = None
def get_v27_recent():
    global _V27_RECENT_CACHE
    if _V27_RECENT_CACHE is None:
        _V27_RECENT_CACHE = load_json(Path('.../v27_recent_signals.json'), {})
    return _V27_RECENT_CACHE
```

### 7. picks缺少zone_type字段

**根因**: `v27_full_scan.py` 的 `generate_picks()` 输出 `signal_type` 但未输出 `zone_type`。前端 dashboard 用 `p.get('zone_type', p.get('engine','?')) `，导致所有选股显示引擎名而非zone类型。

**修复**: 在 `generate_picks()` 中显式添加 `'zone_type': st.get('zone_type', 'OB')`。

## 审计方法论

每次全量扫描后必须验证:
1. **信号完整性**: BOS/CHOCH/MSS/SWEEP/OB/OTE/BPR/PO3 每种信号是否有产出
2. **Zone覆盖**: OB/OTE/BPR三类zone在交易中各占多少比例
3. **字段完整性**: trades必须有全部审计字段(signal_date/entry_date/conf_type/source_event/audit)
4. **前端兼容性**: 所有dashboard/monitor/backtest/analysis/kline模板是否兼容当前数据字段
5. **WR合理性**: WR>80%需检查未来函数或TP设置过近
6. **退出分布**: TP_HIT/SL_HIT比例应接近50/50，极端偏向一边需检查SL/TP逻辑

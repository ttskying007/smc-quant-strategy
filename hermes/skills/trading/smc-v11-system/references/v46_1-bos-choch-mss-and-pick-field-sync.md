# V46.1 BOS/CHOCH/MSS 与前端选股字段同步修复笔记

## 触发症状

- 用户反馈 BOS / CHOCH / MSS 仍需深入修复，SMC 结构信号准确性影响回测和选股。
- 实时/近期选股页出现“无近期选股(45天内)”，但选股页实际存在约 97 只 ACTIVE_CANDIDATE。
- 选股页中“质量 / TP / 序列”为空。
- `/api/picks` 与 `/monitor` 数量不一致。

## 根因

### 1. 45 天近期选股误判

V46.1 当前选股来自 watchlist，ACTIVE_CANDIDATE 是“已确认待跟踪/待入场”的 setup，不一定已经有 `entry_date`。

错误过滤方式：

```python
p.get("entry_date")
```

正确日期链：

```python
pick_date or conf_date or retrace_date or entry_date or signal_date or date
```

实时接口 `/api/live-prices` 和任何“近期选股”过滤都必须使用这条链，否则会把未入场但有效的 setup 误判为空。

### 2. 选股字段为空

V46.1 engine-native 字段与前端旧字段不一致。

前端常读：

```text
score, entry_quality, tp_tiers, ctx_seq, seq, detail, price, dz_low, dz_high
```

V46.1 原始 watchlist 常有：

```text
quality_score, tp1/tp2/tp3, sequence_kind, source_event, zone_type,
conf_type, execution_zone_low/high, entry_price, last_close
```

必须在 engine 生成层或 `_normalize_pick_scope()` 前端归一化层补齐字段，避免页面空白。

推荐补齐：

```python
score = quality_score or score
entry_quality = HIGH/MED/LOW from score
price = entry_price or last_close or current_price
current_price = price
last_close = price
dz_low = execution_zone_low or zone_low
dz_high = execution_zone_high or zone_high
zone_low = dz_low
zone_high = dz_high
tp_tiers = [
  {"price": tp1, "pct": (tp1/price-1)*100, "type": "TP1"},
  {"price": tp2, "pct": (tp2/price-1)*100, "type": "TP2"},
  {"price": tp3, "pct": (tp3/price-1)*100, "type": "TP3"},
]
ctx_seq = sequence_kind + source_event + zone_type + conf_type + entry_mode
seq = ctx_seq
detail = ctx_seq
```

Validation invariant after fix:

```text
missing(score, entry_quality, tp_tiers, ctx_seq, seq, detail, price, dz_low, dz_high) == 0
```

### 3. `/monitor` 数量与 `/api/picks` 不一致

V46.1 ACTIVE_CANDIDATE is setup-level, not symbol-level. The same symbol can have multiple valid structures. Do **not** dedupe by `symbol` on the monitor page for V46.1. Dedupe drops real setups and creates inconsistent counts.

Correct monitor behavior:

```text
/api/picks active count == /monitor 当前有效选股 count
```

### 4. BOS/CHOCH/MSS 审计不能只看聚合指标

Add a full-market structural invariant audit before accepting “structure signal fixed”. Use Pine/LuxAlgo state-machine invariants:

- structure event only after the confirming pivot exists;
- bullish BOS/CHOCH requires `prev_close <= pivot_high` and `close > pivot_high`;
- bearish BOS/CHOCH requires `prev_close >= pivot_low` and `close < pivot_low`;
- CHOCH must be a trend-direction transition;
- MSS must be a CHOCH with nearby same-direction liquidity sweep and displacement/body evidence;
- bad event count must be zero or every sample must be explicitly inspected and classified.

Example output to require:

```json
{
  "files": 4649,
  "events": 53670,
  "bad_events": 0,
  "bad_rate": 0.0,
  "errors_count": 0,
  "checks": {
    "structure_events_nonempty": true,
    "bos_choch_mss_invariants_passed": true
  }
}
```

## Verification checklist

After changing V46.1 structure or watchlist/frontend sync:

1. Compile all touched Python files:
   ```bash
   cd /root/.hermes/scripts
   python3 -m py_compile smc_unified.py v25/v45_1_recall_repair.py v25/v46_1_layered_3y.py v25/smc_core_luxalgo_v34.py
   ```

2. Run full structure audit:
   ```bash
   python3 v25/v46_1_structure_audit.py
   ```

3. Rebuild V46.1 base/watchlist:
   ```bash
   python3 v25/v46_1_layered_3y.py --rebuild-base
   ```

4. Restart frontend and reload cache:
   ```bash
   pkill -f 'python3 smc_unified.py' || true
   cd /root/.hermes/scripts && python3 smc_unified.py
   # then request /api/reload
   ```

5. Verify endpoints:
   - `/api/picks/contract`: active count > 0, historical count 0 for V46.1 watchlist-first mode.
   - `/api/picks`: no missing `score/entry_quality/tp_tiers/ctx_seq/price/dz_low/dz_high`.
   - `/monitor`: count matches `/api/picks`, no TP/quality/sequence blanks.
   - `/api/live-prices`: no “无近期选股(45天内)” when active candidates exist;休市时 should return picks plus rest-market message.
   - `/api/kline_full?...&ver=V46_1`: V46.1 structure signals and highlight chain present.

# SMC V46.1 再次全面 Review：遗漏、缺失、设计问题

生成时间：2026-05-25
审查范围：`smc_core_pine_like.py`、`smc_core_luxalgo_v34.py`、`v45_1_recall_repair.py`、`v46_1_layered_3y.py`、`v46_30_case_autopsy.py`、`smc_unified.py`、当前输出 `/root/.hermes/smc_opt_v46_1_layered_3y/`。

## 结论

当前系统不是“已经完成”的状态。上一轮虽然修了一部分 Pine-like core 和前端命名，但再次审查发现仍有多个阻塞级设计问题：

1. V46.1 当前生产结果来自缓存，`base_info.from_cache=True`，没有使用上一轮新改动重新全量构建。
2. V46.1 分层代码存在未定义变量 `zq`，当前报告已有 146 笔 annotate 错误。
3. 当前 active 回测结果的 kept 151 笔中，129 笔是 C 层弱单；A/B 只有 22 笔，但 A/B 的质量明显更好。
4. 当前 kept 的 20 笔亏损中，18 笔仍然有 `LIQUIDITY_TARGET_TOO_CLOSE_OR_MISSING`，说明“流动性目标不足”被错误允许进入 C 层。
5. V46.1 生产信号主要由 LuxAlgo V34 OB/structure 决定；上一轮修的 `smc_core_pine_like.ob_signals_pine_like()` 并未真正作用到 V46.1 生产 OB。
6. FVG 是当前交易主体（139/151），但 FVG 对标 Pine 的问题仍然大量存在：boundary shift、too wide、no touch。
7. 前端 K线对 V46_1 没有启用 LuxAlgo 混合信号源，V46_1 图表信号仍会和回测信号不一致。
8. 逐笔复盘字段缺失：当前 151 笔 kept 全部缺失 `mfe_pct` / `mae_pct`，无法完成“卖早/没吃趋势/低RR”完整复盘。

---

## 数据证据

当前 `/root/.hermes/smc_opt_v46_1_layered_3y/v46_1_report.json`：

```json
{
  "generated_at": "2026-05-24T23:33:05",
  "base_info": {"from_cache": true},
  "errors_count": 146,
  "base": {"n_trades": 2468, "wr": 69.4, "sl_rate": 30.0, "avg_pnl": 2.46},
  "kept_raw": {"n_trades": 151, "wr": 86.8, "sl_rate": 12.6, "avg_pnl": 4.64},
  "kept_weighted": {"weighted_wr": 92.1, "weighted_sl_rate": 7.6, "weighted_avg_pnl": 6.62}
}
```

Kept 分层质量：

| 分层 | 笔数 | WR | SL率 | AvgPnL | 说明 |
|---|---:|---:|---:|---:|---|
| A+B | 22 | 95.5% | 4.5% | 9.70% | 真正高质量 |
| C | 129 | 85.3% | 14.0% | 3.77% | 当前主体，但弱点明显 |
| 全部 kept | 151 | 86.8% | 12.6% | 4.64% | 被 C 层拖低 |

Kept 结构：

```text
zone_type: FVG 139, OB 12
sequence_kind: CONTINUATION 91, REVERSAL 60
entry_mode: CONFIRM_WICK_RETOUCH_EXEC_HIGH 147, CONFIRM_WICK_RETOUCH_RAW_HIGH 4
conf_type: TWO_BAR_REJECTION_HOLD 151
exit: TRAILING_STOP 125, SL_HIT 17, GAP_TRAILING_STOP 7, GAP_SL_HIT 2
```

亏损20笔问题：

```text
LIQUIDITY_TARGET_TOO_CLOSE_OR_MISSING: 18/20
STRONG_WEAK_CONTEXT_WEAK: 9/20
FVG_NOT_PINE_PARAM_OR_BOUNDARY_SHIFT: 8/20
FVG_TOO_WIDE: 7/20
```

---

## 🔴 阻塞问题

### 1. V46.1 有未定义变量 `zq`，导致 146 笔交易注解失败

位置：`/root/.hermes/scripts/v25/v46_1_layered_3y.py:179,182`

```python
elif zt=='FVG' and seq=='CONTINUATION' and liq>=12 and zq=='MINOR' and not strong_ok:
elif zt=='FVG' and seq=='CONTINUATION' and liq>=12 and zq=='MULTI' and not strong_ok:
```

`zq` 没有定义。当前报告已经记录：

```json
"errors_count": 146,
"error": "name 'zq' is not defined"
```

影响：
- 146笔交易没有被正确分层；
- kept/rejected统计不完整；
- 当前V46.1指标不是可信全量指标；
- `errors_count` 没有进入验收失败条件，导致错误被“带病通过”。

修复：
- 明确定义 `zq`：例如根据 `raw_zone_width_pct` 或 FVG width/ATR 分类为 `MINOR/MULTI/WIDE`；
- 或删除这两个分支，改为已有 `FVG_TOO_WIDE`/`FVG_BOUNDARY_SHIFT`规则；
- 验收条件必须加入 `errors_count == 0`。

---

### 2. 当前结果来自缓存，没有重新全量构建

位置：`v46_1_layered_3y.py:249-255`

```python
if cache_file.exists() and not limit:
    return load_json(cache_file), ..., {'from_cache': True}
```

当前报告：

```json
"base_info": {"from_cache": true}
```

影响：
- 上一轮对 `smc_core_pine_like.py` 的OB、Sweep修复没有被重新跑进base；
- 报告和前端展示仍可能是旧信号定义生成的数据；
- 任何“已修复”的结论都不能成立。

修复：
- 必须删除/刷新 `base_v45_1_3y_*.json` 后重跑；
- 或增加 `--rebuild-base` 参数；
- 验收报告必须输出 `definition_hash` / `source_file_mtime`，证明数据来自当前代码。

---

### 3. V46.1 生产OB并没有使用上一轮修复的 Pine-like OB

位置：`v45_1_recall_repair.py:67-80`

```python
res32 = v41.v32a.detect_all_signals_pine_like(kl)
res34 = v41.v34core.detect_all_signals_lux_v34(kl)
sig = res32['signals']
sig['sweeps'] = merged
sig['swing_structure'] = res34['signals'].get('swing_structure', [])
sig['internal_structure'] = res34['signals'].get('internal_structure', [])
sig['structure'] = res34['signals'].get('structure', [])
sig['obs'] = res34['signals'].get('obs', [])
```

影响：
- 上一轮修复的 `ob_signals_pine_like()` 对当前V46.1生产OB无效；
- 当前V46.1 OB来自 `smc_core_luxalgo_v34.order_blocks_from_structure()`；
- 用户问“是否所有SMC信号对标Pine脚本”时，答案仍是：没有，当前是混合代理，不是统一Pine对标。

修复：
- 在 `smc_core_luxalgo_v34.order_blocks_from_structure()` 内加入同样的 displacement/body/min_strength 字段；
- 或明确将 V46.1 的 OB 改为 Pine/SMC2026 profile 的 OB，并同步前端；
- 输出中必须保存 `ob_source_core` 字段。

---

### 4. V46.1 前端K线信号没有对齐当前active版本

位置：`smc_unified.py:2874`

```python
if ver in ('V41', 'V40', 'V39', 'V38', 'V37', 'V36', 'V34D'):
    lux_sigs = _lux_core.detect_all_signals_lux_v34(data)['signals']
    sig_data['structure'] = lux_sigs.get('structure', [])
    sig_data['sweeps'] = lux_sigs.get('sweeps', [])
    sig_data['obs'] = lux_sigs.get('obs', [])
```

这里没有 `V46_1`、`ACTIVE_VERSION`、`V45_1`。因此访问 `ver=V46_1` 时：
- K线图使用 Pine-like structure/sweep/OB；
- 回测/选股使用 V45.1/V46.1 的 LuxAlgo structure/sweep/OB；
- 图表标记和交易链仍可能不同步。

修复：
- 将条件改为包括 `V46_1` 与 V45.x；
- 或根据 trade 的 `base_engine/definition_version` 决定signal core；
- K线接口返回 `signal_core_used`，前端可见。

---

### 5. 分层逻辑允许明显亏损根因进入 kept C层

位置：`v46_1_layered_3y.py:130-194`

当前逻辑：

```python
elif liq>=5:
    layer='C'; size=0.35
```

但数据证明：20笔亏损里18笔有 `LIQUIDITY_TARGET_TOO_CLOSE_OR_MISSING`，且 C层占 kept 主体：129/151。

影响：
- 当前系统靠降仓掩盖低质量，不是信号修复；
- “保证胜率和盈亏比”无法依赖 C层；
- A/B质量远高于C：A+B 22笔 WR 95.5%、AvgPnL 9.70%，C层 WR 85.3%、AvgPnL 3.77%。

修复：
- 当前正式选股只输出A/B；
- C层作为观察/微仓，不进入主交易；
- 对C层进一步拆：`target 5-8 + weak context` 必须拒绝；`FVG boundary shift + too wide` 必须拒绝。

---

### 6. FVG是主体，但FVG对标仍未完成

当前 kept：FVG 139/151，OB 12/151。

亏损问题中：
- `FVG_NOT_PINE_PARAM_OR_BOUNDARY_SHIFT`: 8/20
- `FVG_TOO_WIDE`: 7/20

`smc_core_pine_like.py:321-352` 的 FVG逻辑：
- 没有严格按用户截图中的3色/连续K线模式分级；
- `fvg_min_gap_atr=0.12` 太松；
- `delta_pct >= auto_thresh * 0.35` 过松；
- mitigation只记录字段，不在信号层做完整生命周期状态。

修复：
- FVG分为：strict SMC2026 FVG、wide FVG、boundary-shift FVG、unmitigated FVG；
- 交易只用 strict + touched/mitigated；
- wide/boundary-shift 只能观察，不交易。

---

### 7. 回测缺少 MFE/MAE，无法完成“出场是否卖早/没吃趋势”复盘

当前 kept 151笔：

```text
missing mfe_pct: 151/151
missing mae_pct: 151/151
```

影响：
- 无法判断低RR是：目标太近、trailing太早、没吃到趋势、还是入场错误；
- “逐笔分析出场价格”缺少核心证据；
- 当前 `replay_audit()` 只是占位：`post_sl_behavior='needs_forward_replay'`。

修复：
- `backtest_v34_setups()` 必须输出：MFE、MAE、max_favorable_date、max_adverse_date、post_exit_10/20/40bar、exit_efficiency = realized/MFE；
- 对每笔SL/Trail判断：是否正常止损、卖早、被洗出去、还是信号失效。

---

### 8. `v46_30_case_autopsy.py` 使用旧数据源 `smc_opt_v45_4`

位置：`v46_30_case_autopsy.py:25`

```python
SRC=ROOT/'smc_opt_v45_4'
```

影响：
- V46.1分层依赖的 autopsy 规则来自旧V45.4样本；
- 当前V46.1 kept/removed 不一定被逐笔复盘；
- `SMC2026_PROFILE` 与实际V46.1生产profile并未统一。

修复：
- autopsy 数据源改为当前 active base/kept/rejected；
- 每次生成V46.1同时生成 autopsy，不允许脱节。

---

## 🟡 重要设计问题

### 9. “混合信号源”没有显式数据契约

现在实际是：
- Pine-like：FVG/BPR/EQL/LV/OTE；
- LuxAlgo：structure/sweep/OB；
- SMC2026 audit：另一个profile作为判定参考。

问题不是混合本身，而是没有记录：
- 每个交易使用哪个core；
- 每个信号的profile参数；
- 每个zone是否visual/pine/audit匹配。

建议：每个 setup/trade 必须带：

```json
{
  "signal_core_contract": {
    "structure_core": "luxalgo_v34",
    "ob_core": "luxalgo_v34 or smc2026",
    "fvg_core": "pine_like_v32a",
    "audit_core": "smc2026_profile",
    "profile_hash": "..."
  }
}
```

---

### 10. OB当前交易占比极低，说明OB主方向仍没解决

当前 kept：OB只有12笔，占7.9%。而用户主要质疑的是OB准确性。

这说明：
- 系统不是“修好了OB”，而是几乎不用OB；
- OB被大量拒绝：rejected中OB 254笔；
- OB overlap 0.35-0.65 仍被允许为C层，但大部分OB质量弱。

建议：
- 单独做 OB-only 回测与图表逐笔验证；
- 不要把FVG高胜率掩盖OB识别问题；
- OB至少要输出：source swing、break event、displacement ratio、min_strength、visual overlap、zone candle index。

---

### 11. `replay_audit()` 目前是假审计

位置：`v45_1_recall_repair.py:346-350`

```python
'signal_exists': True,
'signal_correct': True,
'entry_waited_raw_zone': True,
'post_sl_behavior': 'needs_forward_replay'
```

这是硬编码，不是真正逐笔审计。

影响：
- 报告会显示“signal_correct=True”，但没有验证；
- 用户要求逐笔验证，这个字段会造成误导。

建议：删除硬编码，通过实际复盘脚本填充。

---

### 12. Active picks 仍来自历史交易，不是当前未完成状态机

位置：`v46_1_layered_3y.py:288-300`

```python
cand=[t for t in trades if dkey(t.get('entry_date'))>=cutoff and t.get('v46_1_layer')!='REJECT']
```

影响：
- picks是近期历史交易筛选，不是真正当前“等待回踩/等待确认/已armed”的状态；
- 会把已经退出的历史交易当作选股候选；
- 与 `v45_1_watchlist.json` 的状态机 watch 脱节。

建议：
- picks必须来自 watchlist 的 ACTIVE_CANDIDATE / ARMED_READY，而不是 historical trades；
- historical picks只用于回测展示。

---

### 13. 验收标准不够严格

当前 validation decision：

```python
'CANDIDATE_FOR_REVIEW' if sl_rate_reduced and wr_improved and len(kept)>=30
```

缺失条件：
- `errors_count == 0`
- `base_info.from_cache == False` 或 hash匹配
- `front_end_synced == True`
- `mfe_mae_coverage == 1.0`
- `signal_core_contract_present == 1.0`
- `A/B metrics pass` 与 `C层隔离`

---

## 💭 观察项

### 14. 当前RR低的真正原因不是SL，而是C层弱目标 + trailing主导

当前 kept：
- avg risk 3.94%
- avg RR 1.5
- exit中 `TRAILING_STOP + GAP_TRAILING_STOP = 132/151`

不是简单“止损太宽/太窄”，而是：
- C层多数目标空间只有5-8%；
- continuation占比高；
- trailing接管几乎所有出场；
- 缺少MFE/MAE无法证明是否卖早。

### 15. A/B层已经证明方向正确

A/B层：22笔，WR 95.5%，SL 4.5%，AvgPnL 9.70%。

这说明：
- 高质量条件确实有效；
- 当前问题不是完全重来，而是把C层从正式信号中隔离，并重新设计FVG/OB弱桶。

---

## 修复优先级

### P0 必须先修
1. 修复 `zq` 未定义，并将 `errors_count==0` 纳入验收。
2. 强制重建base，禁止继续用旧缓存证明新代码。
3. 前端 `V46_1` K线信号切换到和回测一致的LuxAlgo/Pine混合源。
4. picks改为watchlist状态机，不再从历史交易截取。

### P1 信号定义修复
5. LuxAlgo OB加入 displacement/body/min_strength字段或统一到SMC2026 OB。
6. FVG严格化：3色/ATR/Touch mitigation/boundary shift 分层。
7. C层隔离：正式交易只A/B，C层观察/微仓。

### P2 复盘与RR
8. 回测输出 MFE/MAE/post-exit forward replay。
9. 用 exit_efficiency 判断trailing是否卖早。
10. 重新设计分批止盈/runner，而不是只看聚合RR。

---

## 当前状态判断

- 信号定义：未完全对标 Pine。OB/FVG/Sweep/structure仍是混合实现，且V46.1生产OB未用上一轮修复。
- 组合信号：L1/L2/L3方向正确，但C层放得太松，亏损根因仍进入kept。
- 回测：当前报告不可信为最终验收，因为有146个注解错误且使用缓存。
- 选股：未完成，当前V46.1 picks来自历史交易，不是状态机watchlist。
- K线图表：V46_1未进入LuxAlgo混合信号条件，仍可能不同步。
- 分析复盘：未完成，缺MFE/MAE，replay_audit存在硬编码。

最终结论：需要继续修复，不能标记“所有任务完成”。

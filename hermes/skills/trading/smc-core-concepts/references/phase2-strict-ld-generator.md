# Phase2 Strict L→D Generator Repair Pattern

Use this reference when Phase2 / SMC 回撤系统胜率异常偏低、旧版本高胜率与严格语义不一致，或需要在同步前端/生产之前先重建全市场严格 L→D setup 生成器。

## Core Lesson

不要用旧 overlay、高 WR 历史结果、或确认前入场的质量回测证明 Phase2 POI 回撤策略有效。先隔离生成器，按真实时间顺序重建：

```text
SSL_SWEEP -> BULL_DISPLACEMENT -> DEMAND_POI -> RECLAIM_ENTRY
```

前端/生产同步必须等全市场严格回测和语义审计通过后再做。

## Required Diagnostic Sequence

1. **先查信号源同源性**
   - 对比生产扫描、质量回测、历史版本是否使用同一 detector / registry。
   - 如果 V26 detector 与 V22 signals_v22 语义不同，不可直接比较 WR。

2. **审计时间顺序污染**
   - 分离 `entry before confirmation` 与 `entry after confirmation`。
   - 旧质量回测若大量 entry 在 confirmation 前，高 WR 不可采信。

3. **审计历史高胜率版本是否真 POI 回撤**
   - 检查 `retrace_index == conf_index == entry_index`。
   - 若 100% 无等待回撤，本质是确认后突破/早入场系统，不是 Phase2 回撤系统。

4. **隔离 Strict L→D generator**
   - 不碰前端、不碰生产文件。
   - 单独脚本读取全市场 K 线缓存，生成严格 L→D setup。
   - 全市场 4655/4900+ 股票验证，不能只用几百只样本下结论。

5. **按机制桶筛选，不做表面调参**
   - 至少分桶：`rr_target`、`zone_type`、`risk_bin`、`retrace_bin`、`exit_reason`、`year`。
   - OB 与 FVG 不可混用结论；A 股日线中 OB 桶可能为负期望，应独立剔除。

## Candidate Pattern Proven in Session

全市场严格 L→D 候选：

```text
name: Phase2_Strict_LD_FVG_RR08_Risk6_8
sequence: SSL_SWEEP -> BULL_DISPLACEMENT -> FVG_DEMAND -> RECLAIM_ENTRY
filters:
  zone_type: FVG_Demand
  rr_target: 0.8
  risk_pct: 6.0..8.0
```

Observed full-market audit:

| Metric | Value |
|---|---:|
| stocks | 4655 |
| trades | 6936 |
| WR | 64.39% |
| avg_pnl | +1.0395% |
| SL rate | 35.52% |
| TP rate | 64.32% |
| T+1 same-day exit | 0 |
| semantic order failures | 0 |
| missing required fields | 0 |

Important rejected buckets:

| Bucket | Result | Decision |
|---|---:|---|
| OB_Demand | negative avg expectancy | reject |
| OB_FVG_Demand | negative avg expectancy | reject |
| FVG_Demand | positive expectancy | keep |

## Implementation Contract

Candidate JSON should include:

- `liq_date`, `confirm_date`, `zone_date`, `entry_date`, `exit_date`
- `zone_type`, `zone_low`, `zone_high`
- `entry_price`, `sl`, `tp1`, `risk_pct`, `retrace_pct`
- `exit_reason`, `pnl_pct`, `hold_bars`
- `semantic_order_pass`, `t_plus_1_pass`, `frontend_synced=false`, `production_synced=false`

T+1 rule:

```python
for j in range(entry_idx + 1, min(len(ks), entry_idx + max_hold + 1)):
    ...
```

Never allow same-day exit in A-share backtests.

## Reporting Pattern For Lei

Use compact tables:

1. Candidate version and filter contract
2. Full-market metrics
3. Audit gates: missing fields / temporal order / T+1
4. Rejected buckets and why
5. Explicit sync state: frontend not touched, production not touched

Do not claim production completion until the candidate is wired into scan, API, K-line, live page, and frontend caches and then verified end-to-end.

# V103 信号偏少 / Active Watchlist 根因审计模式

## 触发场景

用户反馈：
- 当前选股/持仓页面信号明显偏少，例如只显示 1 只；
- 要求**不碰入场、不碰信号**，先全面分析底层原因；
- 需要回答每个股票 DNA、每个周期、组合信号数量、先后顺序、间隔、是否存在聪明钱/大资金结构行为。

## 核心结论模式

遇到“信号偏少”不要直接放宽信号、入场或生产门禁。先区分四类数量：

| 层级 | 含义 | 常见误判 |
|---|---|---|
| 底层事件/候选 | 全市场3年 raw candidates/trades | 以为这里少，其实通常不缺 |
| 生产池 | production whitelist + risk/MTF/TP合同后的高质量交易 | 高质量但数量被压缩 |
| active/watchlist 文件 | 当前前端读取的数据源 | 可能只是历史 active 代表行，不是真实未平仓 |
| 前端可见窗口 | current-month/latest-date 过滤后的展示结果 | 最容易把 3 只压成 1 只 |

V103 审计发现的典型链路：

```text
全量3年候选/交易 15275
  → REVERSAL合同候选 5039
  → BOS合同候选 10236
  → V100 A_PRODUCTION_CORE 58
  → V102 balanced_volume_gate 160
  → V103A生产池 171
  → v103a_active_picks 文件 3
  → V88 current-month/latest-date 前端窗口 1
```

关键判断：**底层信号不缺，少的是生产/展示链路被压得过窄**。

## 必做审计步骤

### 1. 追踪数据源，不要先改信号

检查生成层：
- `v103a_risk_gate.py` 是否只把 `enriched_active` 中 `production_eligible_v102=True` 写入 active。
- `v100_active_picks.json` / 当前 active 源文件是否本身只有少量历史代表行。
- active 文件里的行是否已有 `exit_reason=TP2_MAIN_HIT` / `SL_HIT`；如果有，它们不是实时未平仓持仓。

检查前端层：
- `smc_unified.py:_latest_v88_scanner_rows()` 是否按 latest market month / latest date 过滤。
- `/api/picks` 是否读取 active 文件而非 full candidate/watchlist。
- `/monitor` 与 `/live` 是否把历史 active representative 当“当前持仓”。

### 2. 输出压缩漏斗

必须输出表格：

| 层级 | N | Net WR≥0.8 | SL率 | Avg Net |
|---|---:|---:|---:|---:|
| 全量候选/交易 | ... | ... | ... | ... |
| REVERSAL合同候选 | ... | ... | ... | ... |
| BOS合同候选 | ... | ... | ... | ... |
| 生产资格风险前 | ... | ... | ... | ... |
| 当前生产池 | ... | ... | ... | ... |
| active文件 | ... | ... | ... | ... |
| 前端可见窗口 | ... | ... | ... | ... |

### 3. 输出 REVERSAL/BOS 分层，不混池

- REVERSAL 生产白名单可继续高质量；
- BOS 数量通常多，但若 WR/SL 未达生产标准，只能作为 WATCH_ONLY/CANDIDATE；
- 不要为了增加数量把 BOS 直接混入 REVERSAL 生产池。

典型 V103 结论：
- REVERSAL: 5039 笔，但最终生产 171 笔；
- BOS: 10236 笔，数量多但质量约 WR 58% / SL 41%，不可直接进生产。

### 4. 每股 DNA × 周期 × 组合矩阵

输出 CSV，至少包含：

```text
symbol,total,rev_n,bos_n,prod_n,dna_behavior,best_event,main_force,
dna_wr,dna_avg,weekly_phase,daily_phase,m60_phase,rev_wr,bos_wr,prod_wr
```

同时输出总体 DNA 分布：
- CONTINUATION_OR_BREAKOUT_SPECIALIST
- REVERSAL_SPECIALIST
- WATCH_ONLY_NO_TRADE_SAMPLE
- RANGE_ROTATION_CANDIDATE
- CONTINUATION_OR_PULLBACK_CANDIDATE

### 5. 信号先后顺序与间隔

对每类组合输出 bar 间隔：

| 组合 | 标准顺序 |
|---|---|
| REVERSAL_SSL_CHOCH_DEMAND_OB_STRUCTURAL_5R | SSL Sweep → CHOCH → Demand OB/POI → Touch → Reclaim → Entry |
| CONTINUATION_BOS_PULLBACK_STRUCTURAL | BOS → broken structure hold → Demand/OB retest → Reclaim/Entry |

必须统计：
- `sweep_to_event`
- `event_to_zone`
- `zone_to_touch`
- `touch_to_reclaim`
- `reclaim_to_entry`
- `event_to_entry`

注意：如果 `reclaim_to_entry` 中位数为 -1，通常表示 `zone_mid_limit anticipation`：先在 POI 触碰时挂限价/预埋，后一根才确认 reclaim。不要误判为未来函数，但要在报告里解释清楚。

### 6. “大资金在操作”的表达边界

不能用 SMC 结构直接宣称真实大资金。

正确表述：
- 现有 K线数据可证明结构行为：SSL sweep、CHOCH、BOS、Demand OB、POI reclaim、MIXED_ACCUMULATION；
- 但缺少逐笔成交、盘口委托流、龙虎榜、大宗交易，不能证明真实资金主体。

报告里写：

> 可以证明结构上存在“扫流动性→回收→需求区反应”的 SMC 行为，但不能直接证明真实大资金成交。

## 推荐产物

在对应版本目录输出：
- `v103_signal_scarcity_root_cause_v2.md`
- `v103_signal_scarcity_root_cause_v2.json`
- `v103_signal_scarcity_gate_table.csv`
- `v103_signal_scarcity_rev_failure_reasons.csv`
- `v103_signal_scarcity_active_debug.csv`
- `v103_signal_scarcity_month_distribution.csv`
- `v103_signal_scarcity_per_stock_cycle_contract.csv`
- `v103_signal_scarcity_stock_dna_matrix.csv`
- `v103_signal_scarcity_cycle_counts.csv`

## 安全落地原则

| 可以做 | 不要做 |
|---|---|
| 修正 active/watchlist 数据源语义 | 不改入场 |
| 生产池/观察池双层展示 | 不放宽信号定义 |
| 展示每只票 SMC 故事链与间隔 | 不用 WR 表面调参伪造数量 |
| 对 REVERSAL 非生产候选做独立桶审计 | 不把 BOS 直接混入生产 |

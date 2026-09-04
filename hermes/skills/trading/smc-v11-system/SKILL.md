---
name: smc-v11-system
version: 37.8
description: >-
  SMC全量回测+前端系统。V41(2026-05-23): 在V40 replay autopsy基础上继续按“选股正确性→入场正确性→出场正确性”三段复盘。用户明确要求先确认信号是否存在且正确，再检查入场点，再检查出场是否卖早/没吃趋势；聚合WR/RR不能替代逐笔复盘。V41只做安全持仓微调(max_hold 75→120)，保留V40小比例止盈+45% runner+6R trailing，拒绝激进长持仓方案(WR降至76.9%、SL升至23.1%)；正式: 13笔/WR92.3%/SL率7.7%/avgPnL4.51%。前端:8890(V41默认)。
  
  V42+分诊：信号→入场→市场→出场；发布前必须 current-smoke。历史优势/当前扫描/shadow 与因果证据冲突，或处理事务行情、EMPTY_BOOK、BUY_VALID 时，见 `references/causal-production-rebuild-empty-book.md`。事务化全市场 K 线 epoch、promotion journal/崩溃回滚、checksum 故障注入和唯一 production registry 的实现验收见 `references/transactional-kline-epoch-production-registry.md`。

V47 rebuild/provenance audit lesson: when `--rebuild-base` is silent, verify the Python child CPU/process state before killing; parent bash waiting is normal. If `OB_TRADE_MISSING_WAVE_TURN_LABEL` appears, first inspect nested `source_signal.wave_turn_label` versus top-level fields — often the signal is correct and the bug is a trade-output contract/provenance promotion issue. See `references/v47-rebuild-provenance-audit.md`.FVG continuation 里要把 8-12% 的中位流动性陷阱和 12+% 的高质量继续单分开处理：前者可硬拒绝，后者通常只应降权不删除。V46.1 P0前端/回测同步修复流程见 `references/v46_1-p0-frontend-backtest-sync.md`；若前端出现“当前版本暂不支持重跑/当前无有效 ACTIVE_CANDIDATE/K线仍非V46.1/架构文档旧版”，按 `references/v46_1-frontend-active-pick-kline-doc-sync.md` 修复：注册V46_1重跑、watchlist-first选股、缓存失效、K线默认V46_1、文档同步、并重启8890后用HTTP逐入口验证。详情见 `references/v46_1-continuation-mid-liquidity-trap.md`。



user-invocable: true
user-invocable: true
metadata:
  category: trading
  emoji: "⚡"
  tags: [smc, v20, v20.2, smc-setup, v19, v18, v17, luxalgo, leg-detection, hh-hl-ll-lh, ob-at-choch, pine-exact, entry-at-zone, t1-compliance, multi-source-tpsl, free-combo-mining, liquidity-structure-poi]
  supersedes:
    - smc-v84-engine
    - smc-v10-system
    - references/combo-signal-structural-audit.md
    - references/live-monitor-v3-ld-pipeline.md
    - references/ob-bull-final-proof.md""",
    - references/data-refresh-workflow.md
    - references/t1-monitoring-pitfalls.md
    - references/frontend-echarts-pitfalls.md
    - references/v4-full-multi-window-backtest.md
    - references/combo-signal-structural-audit.md
    - references/live-monitor-v3-ld-pipeline.md
    - references/ob-bull-final-proof.md""",
    - references/frontend-echarts-pitfalls.md
    - references/v20-smc-setup-methodology.md
    - references/v19-entry-price-staleness.md
    - references/v20-multitf-pipeline.md
    - references/v20-free-combo-mining.md
    - references/v17-entry-at-zone.md
    - references/v11-final-conclusions.md
---

# SMC 信号系统 — V9.0 自适应+全序列+交易明细 (2026-05-14 最新)

## ⭐ V27 — Strict Event-Based Core + Full Audit Framework (2026-05-20)

V27 (`smc_core_v27.py`, 1237行) is the current production signal engine.
Complete SMC signal pipeline: confirmed swings → state-machine BOS/CHOCH/MSS → event-anchored OB/OTE/BPR → sweep with reclaim → PO3 three-phase → bullish setup builder → T+1 backtest.

### V40 Replay Exit Autopsy (2026-05-23)

See `references/v40-replay-exit-autopsy.md` for the durable replay workflow: diagnose SMC iterations in order — signal/selection correctness, then entry correctness, then exit correctness. V40 fixed the session's main defect: V39 signals were mostly correct but exits sold too early (post-exit continuation in 10/13 within 5 bars and 11/13 within 10 bars). The resulting exit pattern uses smaller partials, a 45% runner, max_hold 75 bars, and delayed 6R trailing.

### V38 Pine gap closed signal audit (2026-05-23)

See `references/v38-pine-gap-closed-signal-audit.md` for the complete P1-P4 closure pattern: BRK/RB definitions, EQL/EQH sweep-source merge, all-signal candidate gating, K-line marker synchronization, frontend V38 rerun support, and the durable rule that implemented/displayed signals must not be promoted to trading unless full-market quality gates pass.

### V27.1 Key Fixes (2026-05-20)
- BPR: anchor to nearest structure event, min_width 0.3%→0.5%, 100-bar time window (O(n²)→O(n×k))
- MSS: sweep precursor required (recent_sweeps tracker, 20-bar window)
- zone_idx>entry_idx guard: removed 279 stale trades
- prev_trend variable scope: use old_trend before trend update
- Frontend: V11→V27 default, date normalization, memory caching (0.3s pages)
- Picks: active-state filtering (6,934 ACTIVE + 17,368 HISTORICAL)
- Audit + performance: see `references/v27-audit-and-performance.md` and `references/frontend-sync-patterns.md`
- **⚠️ V28前端字段映射陷阱**: `references/v28-frontend-sync-lessons.md` — V22/V27信号零重合, 7个字段差异, sweep画线修复, 信号排名分析
| Fix | What | Impact |
|-----|------|--------|
| BPR anchor | anchor_event_idx added, nearest struct event | BPR 100% anchored (was 0%) |
| BPR min_width | 0.3% → 0.5% | Filtered noise BPRs, trades 11,573→4,032 |
| BPR performance | 100-bar time window | O(n²)→O(n×k), 60+min→4.4min |
| MSS sweep | sweep prerequisite check | 8,257 MSS all have sweep precursor |
| prev_trend | old_trend capture before update | Eliminated NameError crash |
| zone guard | zone_idx > entry_idx skip | Violations 279→0 |
| Picks state | ACTIVE/HISTORICAL filtering | 31,554→24,302, frontend shows recent only |
| Date format | K-line/trade date normalization | Frontend trades=0 fixed |

V97 structural RR contract lesson: when TP/SL design is wrong because production candidates use fixed micro-R ladders (`0.8R/1.5R/3R`, `1R/2R/3R`), do not simply set TP to 5R. First find SMC structural targets (BSL/EQH/major high/supply POI/BOS/CHOCH target), compute natural target-space RR, then production-gate by `TP2_R>=5` and `TP3_R>=8`; insufficient target space becomes WATCH_ONLY/reject. See `references/v97-structural-rr-contract.md`.

### V46.1 OB Waves Turn Anchoring

- **OB 波浪锚点硬约束**：OB 准确性不能只靠 displacement 或数量下降。Bull OB 必须靠近 Waves `HL/LL/L`，Bear OB 必须靠近 Waves `HH/LH/H`，且 K 线图必须绘制 HH/HL/LH/LL 波浪与标签。详见 `references/v46_1-ob-wave-turn-anchoring.md`。
- **V47 source-field契约审计**：检测器修好不等于回测/选股/前端已同步；必须验证 `source_signal`、`wave_turn_*`、FVG `gap_*` 从 detector→zone→setup→trade→watchlist→frontend 全链路保留。P0：OB trade缺 `wave_turn_label`、FVG缺gap bounds、时间线/价格越界、前端缺 `wave_swings`、历史交易伪装选股。Replay-only出入场实验只能定位方向，不能当生产回测。详见 `references/v47-wave-turn-ob-replay-audit.md`。

### V27.1 Full Scan Results
4,905 stocks | 261.8s | 47,448 trades | WR=59.7% | Avg PnL=+6.44% | RR=3.69x
OB: 34,445 (60.8%) | OTE: 8,971 (60.5%) | BPR: 4,032 (49.2%)
Picks: 24,302 total (6,934 ACTIVE)

### Audit Framework
7-point audit (see `references/v27-core-audit.md`):
BOS/CHOCH · MSS · OB anchor · OTE future leak · BPR opposing FVG · SWEEP reclaim · Data consistency

V49 90日闭环复盘门禁（详见 `references/v49-closed-loop-90d-review.md`）：当问题是持仓太久、盈利太小、盈亏比太低、卖早/跑早时，必须逐笔检查持仓≤90日、盈利≥2%、亏损噪音>-1%、盈利≥2R、risk_pct≥1%，并在退出后继续追踪90日 MFE/MAE、卖早/卖晚、MFE捕获率；闭环摘要/问题计数/最差交易必须同步到复盘页与 API。
Run `execute_code` audit script after any core/scanner change.

### V46.1 MSS / bootstrap / OB-FVG alignment

When BOS/CHOCH/MSS counts look sparse or chart MSS disagrees with trade entries, follow `references/v46_1-mss-bootstrap-ob-fvg-alignment.md`.

Critical rules:
- Split MSS semantics: `is_mss` = chart/display early-warning; `is_mss_confirmed` = trading reversal gate.
- Patch the actual V46.1 consumption chain (`v45_1_recall_repair.build_symbol()`), not only older `v34c_next_open.py`.
- Use `bootstrap_cutoff = size`, not `size * 2`; the latter over-filters confirmed pivots for Swing Length 5.
- Keep FVG raw Pine three-candle boundaries separate from executable/trading filters.
- After structure edits, verify full audit, full rebuild, `/api/reload`, `/api/picks`, `/monitor`, and `/api/kline_full` structure labels.
- V46.2 LuxAlgo currentLevel audit: active structure must use `leg(size) -> currentLevel -> crossed`; wave/fractal pivots are reference only. After SMC signal fixes, audit pivot_rule, crossover/crossunder, pivot→break lines, nearest reverse-candle OB, internal+sweep MSS, kept-trade source回链, and分批出场 `exit_legs/exit_price_effective/exit_price_final/exit_weight_sum`. See `references/v46_2-lux-currentlevel-full-audit.md`.

### Frontend Bug Fixes Compendium
see `references/v27-frontend-fixes.md` — 10 critical bugs and performance fixes:
K-line type mapping · backtest dedup · monitor state filter · 61MB cache · ver_map lazyload · version selector · date format · variable scope · trade_by_sym removal
Audit-first methodology: read code → build audit script → run full scan → data-driven conclusions. Never claim bugs without empirical evidence.

## Pine/LuxAlgo structure alignment notes
- When users provide Pine screenshots/settings, treat `Swing Length` as a first-order structural scale knob, not a minor tuning parameter.
- Split MSS into `is_mss` (early-warning) and `is_mss_confirmed` (strict trade gate) so display and trade logic can diverge safely.
- See `references/v46_1-pine-structure-bos-choch-mss.md` for the repair pattern and verification checklist.

### V27 Key Files
| File | Purpose |
|------|---------|
| `/root/.hermes/scripts/v25/smc_core_v27.py` | Signal engine (1237行) |
| `/root/.hermes/scripts/v25/v27_full_scan.py` | Full scanner + pick generator |
| `/root/.hermes/scripts/v25/v27_adapter.py` | Frontend field mapping |
| `/root/.hermes/smc_opt_v27/v27_trades.json` | 47,448 trades |
| `/root/.hermes/smc_opt_v27/v27_picks.json` | 24,302 picks |
| `/root/.hermes/scripts/smc_unified.py` | Unified frontend (:8890, loads V27 by default) |

## V42/V43/V44/V45/V46 止损/漏单分诊纪律

当 SL_hit / stop_loss 触发较多，或用户问“是信号问题、入场点问题、SMC定义问题、组合方式问题、还是未到入场点位”时，必须先按 `references/stoploss-root-cause-triage.md` 做逐笔根因分桶，再决定是否改参数。不要先放宽 SL、不要只报 WR/RR、不要用聚合指标证明机制正确。


## ⭐ V12 — 详细交易引擎 + 全信号前端重写 (2026-05-15)

V12引擎(15029笔/4702只/WR=99.1%) + 前端全信号渲染(矩形+线段+买卖标记+摆动点+17族开关)。
详见 `references/v12-engine-and-frontend.md`。

### V12 关键文件
- `v12_engine.py` — V12回测引擎
- `smc_unified.py` — 统一前端(8890端口,6页面,全SMC信号渲染+17族开关+HH/HL/LL/LH摆动点)
- `/root/.hermes/smc_opt_v12/v12_complete.json` — 全量结果 (15029笔/4702只/WR=99.1%)
- `/root/.hermes/smc_opt_v12/v12_trade_log.csv` — 详细CSV日志 (32字段规范见 `references/v12-trade-log-specification.md`)

## ⭐ V5 Final — Market-State-Driven System + Timerange Validation (2026-05-14)

V5 uses **market state** (FVG回补率) to gate strategies:
- L1 OB_Bull: always active, WR=93-98%, dominant PnL source
- L2 ALL→ZONE: only in MeanReversion, WR=63-70%, marginal value

Timerange backtest (3088 bullish, 7755 trades): 2024-2025 WR=91.2%, 2026 WR=93.7%.
Best L2 combo: BOS_Bull→FVG (69.3% WR). Market state gating validated.
详见 `references/v5-timerange-validation.md`

### 核心发现
OB_Bull单信号WR=94.2%,无需序列/自适应/多TF。详见 `references/ob-bull-final-proof.md`。

### 选股规则
- T+1: 昨日信号(n-2 bar)→今日入场
- 今日0 OB_Bull是正常的(大盘偏空日)
- 详 `references/t1-monitoring-pitfalls.md`
### 监控系统 V3 — 分层Pipeline (2026-05-14) ⚡

**V3分层扫描器**: `scan_LD_v3.py` → 周线bullish → L1(OB_Bull 89.5%WR) + L2(FVG combo gap≤10 ~78%WR) + L3(FVG combo gap>10 ~72%WR)
监控: `monitor_check.py` V3 → walk-forward全bar检查, merge新picks, SL capped 3%, T+1
Cron: `*/30 * * * *`, no_agent=true
前端: http://localhost:8890/monitor (Dashboard: 6卡片 + 持仓表 + 盈亏表 + 60s刷新)
详 `references/live-monitor-v3-ld-pipeline.md`, `references/combo-signal-structural-audit.md`""",
    - references/live-monitor-v3-ld-pipeline.md
    - references/ob-bull-final-proof.md""",
### 数据刷新
- 腾讯API(需-L),20并发。详 `references/data-refresh-workflow.md`
- 4836只/目标~5400只(缺564待补)

## ⭐ V9.0 — 自适应SMC: 动态SL + 多周期共振 + 状态检测 (2026-05-14)

全量4836只验证。关键发现: **紧SL(zone_low*0.995)最优, 动态SL/60min共振均未超越。**

| 系统 | WR | PnL | 说明 |
|------|-----|-----|------|
| V8.0 (per-stock best + fixed SL) | **80.3%** | +1.19% | ⭐ 当前最优 |
| Global fixed (ZONE_ONLY for all) | 79.4% | +1.09% | 基线 |
| V9a (dynamic SL, no 60min) | 75.3% | +1.15% | ❌ ATR buffer有害 |
| V9b (dynamic SL + 60min共振) | 75.9% | +1.18% | ❌ 过滤有效信号 |

**核心教训**: 
- 自适应价值在模式选择(per-stock best pattern), 不在SL调整
- 紧SL(zone_low下0.5%)最优, 加ATR buffer反降WR
- 60min共振作为硬过滤会丢掉有效信号
- 81%股票ZONE_ONLY最优, 19%受益LIQ→ZONE/CTX→ZONE
- ENTRY_AT_ZONE(回调入场)在序列系统下WR=78.3% < CLOSE=95%

文件: `adaptive_smc_v80.py` (V8), `adaptive_smc_v90.py` (V9)
结果: `smc_opt_v21/adaptive_smc_v80.json`, `smc_opt_v21/adaptive_smc_v90.json`
详见 `references/v80-adaptive-system.md`, `references/v90-dynamic-sl-lessons.md`

## ⭐ V7.0 — 全信号分类 + 13种时间顺序序列 (2026-05-14)

信号7族分类 + 13种时间顺序序列模式, 全量4836验证。

| 排名 | 模式 | WR | N |
|------|------|-----|-----|
| 1 | LIQ→ZONE | 80.3% | 6768 |
| 2 | CTX→ZONE | 79.4% | 6534 |
| 3 | ZONE_ONLY | 79.4% | 45632 |
| 4 | LIQ→CTX→ZONE | 79.3% | 1450 |

做空全部无效(WR<56%)。文件: `full_sequence_backtest_v70.py`, `full_sequence_backtest_v70.json`
详见 `references/v70-sequence-classification.md`

## ⭐ V4.0 — 全量信号组合验证 (2026-05-14)

对4767只股票测试204种信号上下文组合 × 3窗口 × 2周期。
脚本: `combo_validation_v40.py`, 结果: `smc_opt_v21/combo_validation_v40.json`

### 关键发现

| 组合 | WR | N | 股票 |
|------|-----|-----|------|
| BOS_Bull+CHOCH_Bull+MSS_Bull | 97.5% | 396 | 109 |
| BOS_Bull+CHOCH_Bull | 97.4% | 576 | 152 |
| BOS_Bull+OB_Bull | 96.0% | 1024 | 269 |
| CHOCH_Bull+Sweep_BSL | 94.9% | 831 | 223 |
| BOS_Bull+MSS_Bull | 94.3% | 3445 | 823 ← 最大覆盖 |

84%股票的最佳是单信号上下文(FVG_Bear 961只, BPR 734只, Sweep_SSL 477只)。
**结论: 不同股票需要不同信号组合, 选股用S→D序列, 入场确认用上下文组合。**

详见 `references/v40-combo-validation.md`

## ⭐ V4.0 — 全维度多窗口回测 (2026-05-14) ⭐ 最新

全量2836只股票 × 3时间窗口 × 2趋势 × 5序列模式 × T+1交易。

| 系统 | 笔数 | WR | PnL/笔 | 累计PnL | PF |
|------|------|-----|--------|---------|-----|
| Baseline(无过滤) | 7,324 | 76.6% | +2.57% | +18,851% | 5.4 |
| **V4(周线过滤)** | **5,032** | **77.3%** | **+2.66%** | **+13,399%** | **5.6** |
| 变化 | -31% | +0.7pp | +3.5% | — | +3.7% |

多窗口: full bullish WR=84.3%, mid bullish WR=83.6%, recent bullish WR=83.0% — 极稳定。
序列: L→D WR=85.1%(最优), S→D WR=83.3%。做空全部<73%。
覆盖面从408→2836只(vs V3.0, 不再限制必须有60min)。
60min确认: WR=73.7% vs Baseline 82.5% — ❌ 不可用 (仅15%股票覆盖, 确认后WR反降8.8pp)。
时间范围: 2022-2023熊市0做多(正确避空), 2024-2025牛市WR=83.6%, 2026当前WR=79.2%。

详见 `references/v4-full-multi-window-backtest.md`。
脚本: `full_backtest_v4.py`, 结果: `full_backtest_v4.json`

## ⭐ V3.0 → V3.3 — 多周期选股系统 (2026-05-14 最终, 全量数据)

**周线(Hubble+腾讯API) + 日线SMC序列组合 + 60min入场**

数据: 4,836日线(100%) / 4,551 60min(94%, 腾讯) / 4,830周线(100%, Hubble+腾讯+合成fallback)
有效序列: 1,078只(long-only L→D/S→D)

周线覆盖从23%→100%: Hubble补充2038只, 腾讯67只, 剩余6只日线合成。
下载策略详见 `references/data-download-strategy.md`。

**V3.3最终结果 (bullish+S→D, 三窗口一致95%)**:
| 趋势 | 模式 | full | mid | recent |
|------|------|------|-----|--------|
| bullish (754只) | S→D | 95% | 95% | 92% |
| bullish | L→D | 89% | 90% | 100% |
| bearish (193只) | L→D | 86% | 88% | — |

详见 `references/v33-final-backtest.md`。

### 核心发现

| 周线趋势 | 最佳日线组合 | 股票数 | 平均命中率 |
|----------|-------------|--------|-----------|
| bullish | S→D (52%), L→D (48%) | 320 | 93% |
| bearish | L→D (89%), S→D (11%) | 130 | 87% |
| neutral | L→D (65%), S→D (35%) | 613 | 91% |

- **L→D** (流动性扫荡→需求区) 是全市场最强: 2638笔 WR=80.1% PnL=+2.76% PF=6.6
- 熊市中L→D占89% — 抄底需确认流动性扫荡
- 牛市中S→D和L→D各半
- 60min覆盖: 1496/1607 (93%)

### 全维度交叉回测

`scripts/cross_cycle_backtest.py`: 3周期(daily/60min/weekly) × 3窗口(full/mid/recent) × OB_Bull × T+1。
输出: `smc_opt_v21/cross_cycle_v4.json`。日线S→D WR=94.8%三窗口极稳定。

V3基线: Baseline 14,196笔 WR=72.7% vs V3 1,154笔 WR=76.9%。详见 `references/v3-multitf-results.md`。

### 可扩展架构

```python
SIGNAL_CATEGORIES = {  # 新增信号加这里
    'LIQUIDITY_LONG': ['Sweep_SSL','EQL'], ...
    'STRUCTURE_LONG': ['CHOCH_Bull','BOS_Bull','MSS_Bull'], ...
    'DEMAND_ZONE':    ['OB_Bull','FVG_Bull'], ...
}
PATTERNS = {  # 新模式一行定义
    'L→D': {'stages':['LIQUIDITY_LONG','DEMAND_ZONE'], 'gaps':[20], 'direction':'long'},
    ...
}
```

### 关键文件

| 文件 | 说明 |
|------|------|
| `multi_tf_v2_final.py` | V2.0主分析引擎 (周线合成+序列检测+多窗口测试) |
| `stock_signal_matrix.py` | 个股信号效能矩阵 (per-stock×per-window×per-combo) |
| `smc_sequence_engine.py` | V1.0序列策略引擎 (可扩展架构) |
| `multi_tf_db_v2.json` | 个股数据库 (1607只, 可查询选股) |
| `stock_signal_matrix.json` | 个股信号矩阵 (4800只, top-5组合/窗口) |

### 60min数据

下载: 腾讯ifzq API, `http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={prefix}{code},m60,,200`
缓存: `/root/.hermes/kline_cache/{symbol}_60min_500.json` (4551只, 15线程并行~90s)
格式: `[{t, o, h, l, c}, ...]`

### 周线SMC

从日线合成(每5根=1周), 用V20引擎检测CHOCH/BOS+摆动结构判断趋势。
无需额外API, 无外部依赖。

详见 `references/v2-multi-tf-final.md`

## ⭐ V11 FINAL — 全量研究结论 (2026-05-14)

经过V7.0→V11.2全量4836只迭代验证:

### 核心发现

| 发现 | 数据 |
|------|------|
| OB_Bull单信号最优 | WR=94.2% PnL=+2.59% N=13198 |
| FVG_Bull差距巨大 | WR=71.9% PnL=+0.42% N=24573 |
| OB内部已含结构验证 | 91%有HH/HL/LL/LH摆动结构 |
| 外部序列对OB冗余 | LIQ→ZONE/CTX→ZONE仅匹配5-23%OB且不提升WR |
| Per-stock自适应 | 仅+0.2% WR (Global 79.4%→Adaptive 80.3%) |
| 动态SL无效 | V9.0降至75.3% (vs V8.0固定SL 80.3%) |
| 60min共振无效 | V9b降至75.9% |
| 模式漂移仅12% | 88%股票三窗口模式一致 |
| OB vs FVG SL率差3倍 | OB SL率18% vs FVG 56% |

### 最优策略

```
OB_Bull出现 → T+1开盘买入 → SL=OB.lower×0.995 → TP=+3% → 5bar超时
```

不需要序列组合、不需要趋势过滤、不需要多周期确认。

### 数据下载

**腾讯ifzq (公开API, 无需Key)**:
- 日线: `http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz000001,day,,,300,qfq` (需-L跟随重定向)
- 60min: `http://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sz000001,m60,,200`
- 周线: `http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz000001,week,,,200,qfq`
- 格式: `qfqday/qfqweek` 数组中 `[date, open, close, high, low, volume(手)]`

**Hubble API (需Key:123456)**:
- 日/周/月线: `http://43.167.234.49:3101/api/v2/cnstock/stocks?symbol=000001.SZ&interval=weekly&limit=200`
- curl: `-H 'X-API-Key: 123456'`
- 注意: 可能超时, 腾讯优先

**东方财富**: HTTPS有SSL问题, 不建议
**新浪**: 格式复杂, 不建议

### 下载脚本

`scripts/download_weekly_v3.py`: 周线Hubble+腾讯双源, 8并发
`scripts/today_refresh_pick.py`: 日线腾讯20并发刷新+扫描

### 全信号选股

`scripts/all_signals_scan.py`: 不遗漏任何信号类型
- 单信号: 11种 (OB_Bull/Bear, FVG_Bull/Bear, Sweep_SSL/BSL, BOS_Bull/Bear, CHOCH_Bull/Bear, MSS_Bull/Bear, EQL, EQH, BPR)
- 组合信号: 6种 (ZONE_ONLY, CTX→ZONE, LIQ→ZONE, LIQ→CTX→ZONE, +做空版本)
- T+1: 昨日信号→今日入场
- 窗口: 最近2bar (n-2到n-1)

### 监控系统 V3 — 分层Pipeline (2026-05-14) ⚡

**V3分层扫描器**: `scan_LD_v3.py` → 周线bullish → L1(OB_Bull 89.5%WR) + L2(FVG combo gap≤10 ~78%WR) + L3(FVG combo gap>10 ~72%WR)
监控: `monitor_check.py` V3 → walk-forward全bar检查, merge新picks, SL capped 3%, T+1
Cron: `*/30 * * * *`, no_agent=true
前端: http://localhost:8890/monitor (Dashboard: 6卡片 + 持仓表 + 盈亏表 + 60s刷新)
详 `references/live-monitor-v3-ld-pipeline.md`, `references/combo-signal-structural-audit.md`""",
    - references/live-monitor-v3-ld-pipeline.md
    - references/ob-bull-final-proof.md""",
- T+1合规: 当日买入不可卖出
- Cron: `smc-30min-monitor`

### 架构: 信号三分类 + 可扩展序列模式

信号分3大类, 序列按时间顺序排列:

| 类 | 信号 | 用途 |
|----|------|------|
| **LIQUIDITY** (流动性) | Sweep_SSL, Sweep_BSL, EQL, EQH | 止损聚集/扫荡 |
| **STRUCTURE** (结构) | CHOCH_Bull/Bear, BOS_Bull/Bear, MSS_Bull/Bear | 趋势方向/转换 |
| **ZONE** (供需区) | OB_Bull/Bear, FVG_Bull/Bear | POI入场区 |

扩展: 新信号→加入SIGNAL_CATEGORIES注册表, 新模式→加入SEQUENCE_PATTERNS一行定义。

### 全量4800组合回测

| 模式 | 含义 | 交易 | WR | PnL | PF |
|------|------|------|-----|-----|-----|
| Baseline | 无过滤 | 14,196 | 72.7% | +2.11% | 3.9 |
| **Combined** | L→D+S→D+L→S→D | **6,445** | **75.6%** | **+2.44%** | **4.9** |
| **L→D** | 流动性→需求区 | 2,638 | **80.1%** | **+2.76%** | **6.6** |
| L→S→D | 流动→结构→需求 | 510 | 79.4% | +2.69% | 6.1 |
| S→D | 结构→需求 | 1,433 | 76.8% | +2.56% | 5.0 |

核心发现: **L→D (流动性扫荡→需求区) 是最强单模式**。Sweep_SSL出现后20bar内出现OB_Bull/FVG_Bull = 80.1%胜率。
做空(Short)模式WR 64-68%弱于做多, A股T+1限制做空效率。

### V20.2 SMC Setup — 完整流动性→结构→POI流程

首次全面超越Baseline: WR=87.1% (+14.4pp), PnL=+3.52% (+67%), TP率87%。
`detect_smc_setups()`: Demand Zone→SSL Sweep→CHOCH→POI入场 (时间顺序)。

### 个股信号效能矩阵

`/root/.hermes/scripts/v11/stock_signal_matrix.py`: 每只股票×3时间窗口(full/mid/recent)×信号组合命中率矩阵。
输出: `/root/.hermes/smc_opt_v21/stock_signal_matrix.json` (4800只, top-5组合/窗口)。
当前限制: recent窗口仅254只≥3样本 — 大部分股票信号稀疏。

### 关键文件

| 文件 | 说明 |
|------|------|
| `signals_v20.py` | V20信号引擎 (~700行, 14种信号) |
| `smc_sequence_engine.py` | V1.0序列策略引擎 (可扩展架构) |
| `stock_signal_matrix.py` | 个股信号效能矩阵构建器 |
| 前端: `smc_unified.py` port 8890, routes /v19 /v20 |

### 核心教训

1. **时间顺序是必须的** — 窗口内信号集合(无顺序)全部劣于Baseline
2. **L→D > S→D > L→S→D** — 流动性扫荡比结构确认更重要
3. **全量4800回测不可替代** — 200只抽样结论与全量常有偏差
4. **做空在A股效率低** — T+1 + 涨跌停限制做空
5. **个股统计不可行** — 902/4800只有≥5样本, 蓝筹均<5
6. **自由组合挖掘 ≠ 预定义模式** — 数据驱动发现: OB_Bull+看跌上下文=最优, 经典Sweep→CHOCH→FVG→OB非最优
7. **周线SMC趋势 > MA20趋势** — 用CHOCH/BOS方向+最后摆动结构判断, 比简单MA20更准确
8. **10种信号组合全测, 仅2种超越Baseline** — L→D(WR=80.1%)和S→D(WR=76.8%)。其他8种均劣于无过滤
9. **SMC Setup(完整流动性→结构→POI) WR=87.1%** — 交易少但单笔质量最高, 适合精选交易

## V20.2 — SMC Setup: 流动性→结构→POI ⭐ 首次超越Baseline

V20 是对 V19 已知 9 项限制的全面修复, 通过全量 4800 只代码级诊断 + 逐信号根因分析完成。

### V19→V20 6项修复

| # | 信号 | V19 根因 | V20 修复 | 效果 (全量4800) |
|---|------|---------|----------|----------------|
| 1 | OB(SMC) | `strength>=2.0` + `disp>0.6*rng` → 全部返回0 | 降为 1.0 和 0.25 | 0→~4个/股 |
| 2 | CHOCH/BOS | `crossed` 标志永久锁定, 39-50%摆动点未触发 | 去掉crossed, 每bar选最近未超越摆动点 | 动态检测 |
| 3 | Sweep | min_pen=ATR×0.15, 窗口30bar | min_pen=ATR×0.08, 窗口60bar | +465~581% |
| 4 | EQL/EQH | 仅相邻pivot, 0.5%固定阈值 | 全量O(n²)比较 + ATR自适应 | +521~595% |
| 5 | MSS | cooldown=12bar, 窗口40bar | cooldown=5bar, 窗口50bar | +68~79% |
| 6 | 序列窗口 | 固定3-5bar间隔 | ATR%自适应: scale=1.5/atr_pct | 序列+844% |

### V20 全量对比 (4800只)

信号总量: 192,874 → 255,212 (+32%)
Sweep: 6,950 → 42,581 (+512%)
EQL/EQH: 1,663 → 11,068 (+565%)
MSS: 13,231 → 22,885 (+73%)
序列: 393 → 3,711 (+844%), 332→2,562只股票

### 序列窗口 ATR 自适应

`_build_sequences(atr_pct)`: `scale = 1.5 / max(atr_pct, 0.005)`, 窗口 = base_window × scale × atr_scale。
高波(ATR=4%)→窗口×0.5, 低波(ATR=1%)→窗口×1.5。新增12种模式(MSS→FVG→OB, BOS→FVG→OB, CHOCH→OB)。

### V20.1 — CHOCH标签法检测 (2026-05-13)

V20.0 CHOCH/BOS基于 `last_cross_dir` 状态追踪，CHOCH仅2.0/只。V20.1改用**摆动点标签直接判断**:

```
上穿 LH (Lower High) → CHOCH_Bull (下降趋势反转)
上穿 HH (Higher High) → BOS_Bull (上升趋势延续)
下穿 HL (Higher Low) → CHOCH_Bear (上升趋势反转)
下穿 LL (Lower Low) → BOS_Bear (下降趋势延续)
```

核心改进:
- 去掉 `last_cross_dir` 状态追踪 → 纯静态标签判断
- 去掉 "beaten" 过滤 (被后来摆动超越的旧摆动)，允许所有历史摆动点触发
- 每个摆动点仅触发一次 (`fired_swings` set)
- 每bar最多1个high触发+1个low触发

全量4800结果: CHOCH 9,556 → **12,934 (+35%)**, 每只2.0→2.7。
BOS从23,131降至16,270 (V20.0的BOS包含误标为BOS的CHOCH)。

### V20.2 — SMC Setup: 流动性→结构→POI (2026-05-13) ⭐ 首次超越Baseline

全量A股回测发现: 所有信号组合过滤(自由组合/SMC序列)都劣于Baseline。根因: 之前的"组合"只是窗口内信号集合, **未考虑时间顺序和SMC完整流程**。

V20.2实现 **完整SMC入场Setup检测** (`detect_smc_setups`):

**Long Setup (时间顺序)**:
```
Demand Zone(OB_Bull/FVG_Bull) → SSL Sweep(扫流动性) → CHOCH_Bull(结构转换) → POI入场(回到Demand Zone)
```

**Short Setup**:
```
Supply Zone(OB_Bear/FVG_Bear) → BSL Sweep → CHOCH_Bear → POI入场
```

**检测逻辑** (`signals_v20.py: detect_smc_setups`):
- Demand/Supply zone 必须在 Sweep **之前**形成 (20bar窗口)
- Sweep→CHOCH 必须在 30bar 内
- Zone 价格必须接近 swept level (ATR×1.5)
- 每个 zone+sweep+choch 组合 = 1个Setup
- 入场点 = zone的 idx (等待价格回测 zone)

**全量4800回测 — 首次全面超越Baseline**:

| 指标 | Baseline | **SMC Setup** | 变化 |
|------|----------|---------------|------|
| 股票 | 4,283 | 1,732 | - |
| 交易 | 14,196 | 1,732 | -88% |
| **WR** | 72.7% | **87.1%** | **+14.4pp** |
| **PnL** | +2.11% | **+3.52%** | **+67%** |
| **TP率** | 72% | **87%** | **+15pp** |
| SL率 | 27% | 13% | -14pp |
| Hold | 2.1b | 2.9b | +0.8b |

**核心发现**:
1. SMC Setup是**全量A股上第一个在质量指标上全面超越Baseline的策略**
2. 交易量少88%但单笔质量高67% → 更适合精选交易
3. 87% TP命中 vs 72% → 87%的交易以目标价止盈, 仅13%止损
4. 做空同样有效(Setup包含做空方向)
5. **关键教训: 信号组合必须尊重时间顺序, 且必须包含流动性扫描**

**自由组合挖掘教训** (14,196笔交易反向分析):
- OB_Bull单独: WR=85.2% (最强单个信号)
- OB_Bull + 看跌上下文 = WR 88-100%
- 但筛选后交易减少95%, WR反而略降 → 说明组合不提升质量
- **经典 SMC 序列 Sweep→CHOCH→FVG→OB 并非数据中最优模式**

**个股自适应困境**:
- 47,300个入场信号, 每只平均10个
- 仅902/4800只有≥5个样本 (够做个股分析)
- 茅台/平安/宁德等核心蓝筹**全部<5个样本** → 个股策略不可行
- 结论: A股只能用**全市场统一策略**, 不能逐股定制

详见 `references/v20-scm-setup-methodology.md`

### V20 全量对比 (4800只)

Baseline (FVG_Bull+OB_Bull, 无序列过滤): WR=72.7%, PF=3.9, 累计+29,948%
Sequence (仅序列终端入场): WR=72.1%, PF=3.7, 交易减少95%

序列过滤方向错误 — 反降WR 0.6pp。取而代之应使用**自由组合上下文评分**。

详见 `references/v20-backtest-report.md`, `references/v20-free-combo-mining.md`

### 自由组合挖掘 — 数据驱动发现有效模式

对 14,196 笔交易反向挖掘发现: **OB_Bull + 看跌上下文 = 最优**。
- OB_Bull 单独: WR=85.2%
- BOS_Bear + OB_Bull: WR=86.4%
- BPR + OB_Bull: WR=86.9% (N=665, 量大)
- 信号密度 6 个 = 甜蜜点 (WR=77.3%)

经典 SMC 序列 Sweep→CHOCH→FVG→OB 并非数据中最优模式。

详见 `references/v20-free-combo-mining.md`

### V20 文件

| 文件 | 说明 |
|------|------|
| `/root/.hermes/scripts/v11/signals_v20.py` | V20 + V20.1 信号引擎 (~700行) |
| `/root/.hermes/scripts/v11/v20_comparison.py` | V19 vs V20 对比脚本 |
| `/root/.hermes/scripts/v11/choch_compare.py` | V20.1 CHOCH改进对比 |
| `/root/.hermes/smc_opt_v20/v20_signal_comparison.json` | 全量对比结果 |

前端: `/root/.hermes/scripts/smc_unified.py` 已接入 V20 (`detect_all_signals_v20`), 路由 `/v19` `/v20`。

脚本: `scripts/choch_compare.py`, `scripts/full_backtest_v20.py`, `scripts/free_combo_mining.py`
诊断方法论: 见 `references/v20-diagnostic-fixes.md`

---

V19 彻底解决了"OB出现在趋势中途"的核心问题。通过 LuxAlgo leg() 摆动检测替代所有 pivothigh/zigzag 方法。

### 核心架构

```
LuxAlgo leg(20) → HH/HL/LL/LH 标注 → 仅结构点检测信号
```

**leg() 摆动**: `high[leg_size] > ta.highest(leg_size)` — 20根K线前的最高点超过后续20根K线所有高点，确认为摆动高点。在300根A股日线上产~18个纯结构摆动点。

### V19 vs 前代对比

| 指标 | V17(zigzag) | V18(pivot5) | **V19(leg20)** |
|------|------------|-------------|---------------|
| 摆动方法 | zigzag 2% | pivothigh(5,5) | **LuxAlgo leg(20)** |
| 摆动点数 | ~29 | ~25 | **18** |
| HH/HL/LL/LH | 无 | 无 | **✅ 全部标注** |
| OB位置 | 趋势中途 | 部分偏移 | **✅ 仅结构点** |
| CHOCH/BOS | 4 | 2 | **11** |
| Sweep | 8 | 18 | **4** |

### 关键Pine差异（已修复）

1. **OB displacement 是硬过滤**: Pine SMC 2026 line 453 `disp > rng * ob_displacement_mult` — 是硬门控，不是评分。A股适配 multiplier=0.7（Pine默认1.5用于外汇）
2. **LuxAlgo OB 在 CHOCH/BOS 时回溯存储**: `storeOrdeBlock()` 在 crossover/crossunder 时从 pivot 到当前bar找OB，不是预设扫描
3. **CHOCH/BOS 用 crossover/crossunder**: `ta.crossover(close, pivot.price)` 而非手动 `close > last_swing_high`
4. **EQL 用百分比阈值**: A股高价股(茅台1400元)用ATR绝对值阈值无效，改用 `avg_price * 0.5%`

### V19 回测引擎

- **T+1 强制**: `assert exit_idx > entry_idx` 零违反
- **多源 TP**: HH_swing + OB_upper + FVG_upper + CHOCH/BOS — 取最近有效阻力(≥entry×1.015)
- **多源 SL**: LL_swing + OB_lower + FVG_lower + CHOCH/BOS — 取最近有效支撑(≤entry×0.985)
- **MAX_TP封顶**: TP ≤ entry×1.05（防止远距离结构阻力导致P&L虚高）
- **RR过滤**: TP距 ≥ SL距（RR≥1.0）
- **OB去重**: 同一OB bar仅入场一次
- **Exit精确**: exit = TP/SL 价格（不用max(open,TP)吃gap溢价）

### 全量4800结果（入场价修复后）

```
4235 active stocks | 13,742 trades | WR=71.9% | P&L=+2.05% | Hold=2.0b
Exit: TP 71.7% | SL 28.0% | EOD 0.3%
4766 individual JSON files generated
```

### 全量4800结果（入场价修复前——虚高，仅供参考）

```
4671 active stocks | 16,317 trades | WR=99.5% | P&L=+4.14% | Hold=1.0b
Exit: TP 99.5% | SL 0.5%
```

### V19 文件

| 文件 | 说明 |
|------|------|
| `/root/.hermes/scripts/v11/signals_v19.py` | V19信号引擎(~570行) |
| `/root/.hermes/scripts/v11/v19_backtest_engine.py` | V19回测引擎(~195行) |
| `/root/.hermes/scripts/v11/multitf_filter.py` | 周线趋势+60min入场优化 |
| `/root/.hermes/scripts/v11/klines_60min.py` | Tencent 60min K线下载器 |
| `/root/.hermes/scripts/smc_unified.py` | 统一前端(8890端口, V19路由) |
| `/root/.hermes/smc_opt_v19/v19_full.json` | V19全量结果 |
| 前端: `http://HOST:8890/v19?s=SYMBOL` | K线+信号渲染+交易明细 |

### 多周期框架

- **周线趋势**: Hubble API `interval=weekly`, MA20过滤器，熊市股跳过
- **60min入场**: Tencent `ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh600519,m60,,200`
- **60min缓存**: 4552只已缓存于 `/root/.hermes/kline_cache_60min/`

### ⚠️ CRITICAL: ENTRY_AT_ZONE 价格过期 Bug (2026-05-13)

V19 回测使用 `entry_price = sig.lower`（zone价格），但入场在 `confirmed_at` bar。此时 zone 价格已过期（市场已大幅变动），导致 WR 虚高至 99.7%、P&L 虚高至 +18.4%。

**修复**: `entry_price = max(sig.lower, ohlcv[entry_idx]['o'])` → WR 降至 71.9%，P&L 降至 +2.05%。

详见 `references/v19-entry-price-staleness.md`。

### ⚠️ ECharts 陷阱 (V19前端)

1. **markArea 格式**: 必须 `[[{xAxis,yAxis},{xAxis,yAxis}],...]` 而非 `[{data:[...]},...]` — 后者静默失败
2. **dark 主题**: `echarts.init(dom,'dark')` 需单独加载主题文件，不加载时静默失败
3. **read_file 截断**: 默认 500 行限制，配合 write_file 可摧毁整个文件。大文件修改前先备份

详见 `references/v19-frontend-debugging.md`。

### ⚠️ 已知限制

1. **P&L仍然偏高(4.14%)**: 1bar持仓+5%MAX_TP封顶，部分股票TP取到5%上限后1日命中。A股日线gap特性不可改变
2. **EQL仍偏少(2-3个)**: 百分比阈值0.5%在1400元股票上=7元，相邻摆动差通常更大
3. **BPR取top-15**: 全对全重叠检测O(n×m)仍可能产生噪声BPR
4. **60min入场优化未全量验证**: 仅191只周线数据，4552只60min数据
5. **OB(SMC)完全失效**: `detect_ob_smc2026` 输出为0，strength阈值2.0对A股太严。7只代表性股票无一通过。详见 `references/v19-signal-quality-audit.md`
6. **CHOCH/BOS利用率仅50-64%**: `crossed`标志一次即永久锁定，39-50%摆动点从未触发穿越。详见 `references/v19-signal-quality-audit.md`
7. **Sweep几乎全体缺失**: min_pen双阈值+收盘反转条件+30bar窗口，3/7只股票0 sweep。详见 `references/v19-signal-quality-audit.md`
8. **EQL/EQH仅比较相邻pivot**: 0.5%固定阈值不自适应，跳一个pivot就错过。详见 `references/v19-signal-quality-audit.md`
9. **序列窗口固定**: 所有模式3-5 bar间隔，高波/低波股票节奏不同但无自适应。3343/4800股票0序列。详见 `references/v19-signal-quality-audit.md`

### V19 信号质量审计 (2026-05-13)

全量代码trace诊断7种信号类型的检测质量。详见 `references/v19-signal-quality-audit.md`。

诊断脚本: `scripts/signal_diag.py` — 每只股票打印信号数量、根因分析、未触发摆动点。
序列过滤对比: `scripts/seq_comparison.py` — baseline vs sequence-only全量4800回测对比。

序列过滤结果:

| 指标 | 无过滤 | 仅序列 | 变化 |
|------|--------|--------|------|
| 交易股票 | 1,360 | 332 | -76% |
| 交易数 | 5,136 | 393 | -92% |
| WR | 70.8% | **74.6%** | +3.8pp |
| 均盈亏 | +2.05% | **+2.28%** | +11% |
| 0序列股票 | — | 3,343 | 70% |

方向正确(WR↑,PnL↑)但覆盖率不足(过滤92%交易)。序列窗口需自适应化。

### 文件恢复教训（重要）

`read_file` 不带 offset/limit 时默认只读500行，配合 `write_file` 会截断整个文件。修改大型文件时：
- 用 `read_file(limit=N)` 明确指定读取行数
- 或用 `execute_code` 中的 `read_file` + `write_file` 
- 修改前先 `cp file file.bak`

### 核心架构突破

V19 首次正确解决了"OB出现在趋势中途"的根本问题。通过 LuxAlgo leg() 摆动检测，26个摆动点全部正确标注 HH/HL/LL/LH，OB 只附着在确认的结构点上。

### LuxAlgo leg() 摆动检测

LuxAlgo `leg(size)`: `high[size] > ta.highest(size)` → bearish leg (swing high), `low[size] < ta.lowest(size)` → bullish leg (swing low)。 `startOfNewLeg = ta.change(leg) != 0`。

在300bar A股日线上，leg(10) 产出约26个摆动点(13H+13L)，全部是真正的结构转折点。

### HH/HL/LL/LH 标注

LuxAlgo 内部标注：新摆动点与前一摆动比较 → HH (更高高点), LH (更低高点), LL (更低低点), HL (更高低点)。

600519.SH 300bar 完整序列: `LL→HH→HL→LH→HL→HH→LL→LH→LL→HH→HL→HH→HL→LH→HL→LH→LL→LH→LL→LH→LL→HH→HL→LH→HL→LH`

### OB-at-CHOCH-Moment (最关键的架构差异)

LuxAlgo 的 OB 不是在摆动点预设的，而是在 CHOCH/BOS 发生时从 pivot 到当前 bar 之间回溯查找：
- Bullish CHOCH/BOS: 找到 pivot.barIndex 到 bar_index 之间的 min low → OB
- Bearish CHOCH/BOS: 找到 pivot.barIndex 到 bar_index 之间的 max high → OB

这确保了 OB 只发生在结构转换点（CHOCH/BOS位置），而不是趋势中途。

### CHOCH/BOS: 检查所有未交叉pivot

LuxAlgo 检查**所有**未交叉的 pivot，而非仅最新一个：`ta.crossover(close, pivot.currentLevel) and not pivot.crossed`。
修复前 V18 仅检查最新摆动 → CHOCH/BOS=2个。修复后 V19 → 19个(5 CHOCH + 14 BOS)。

### V19 信号对比 (600519.SH 300bar)

| 信号 | V17 | V18 | **V19** | 改进 |
|------|-----|-----|---------|------|
| HH/HL标注 | 无 | 无 | **✅ 26点** | 核心突破 |
| CHOCH | 3 | 0 | **5** | +5 |
| BOS | 6 | 1 | **14** | +13 |
| OB | 39(错位) | 8 | **23** | 结构点 |
| Sweep | 8 | 18 | **11** | 适中 |
| MSS | 9 | 11 | **8** | 干净 |
| FVG | 25 | 17 | **17** | 纯gap |
| EQL | 5 | 1 | **2** | 相邻pivot |
| BPR | 5 | 50 | **46** | 多区域 |

### V19 全量4800回测

```
引擎: V19 LuxAlgo+SMC 2026 + T+1 + 多源结构TP/SL
扫描: 4800只 | 36秒
4799/4800只有交易 | 62,602笔
WR=99.8% | 均P&L=+15.31% | 均持仓=1.0 bar
⚠️ WR异常高因TP最近阻力位(1-3%), 需MIN_PROJECTED_RR过滤
```

### V19 回测引擎关键修复 (2026-05-13)

6项代码级修复, 详见 `references/v19-backtest-fixes.md`:
1. P&L通胀: `exit_price = max(open, TP)` → `exit_price = TP`
2. MAX_TP封顶5% → P&L从+9.70%→+4.14%
3. OB去重防同bar重复入场
4. T+1断言移到EOD之后
5. EQL百分比阈值 `avg_price*0.5%`
6. BPR top-15最近排序

### V20 多周期管线 (2026-05-13)

周线趋势过滤 + 日线信号 + 60min入场优化。详见 `references/v20-multitf-pipeline.md`。

### delegate_task 超时陷阱
`delegate_task` 对复杂文件创建不可靠(3个全600s超时)，应直接用 `write_file` + `terminal test`。

### V18 Pine对比方法论
详见 `references/v18-pine-comparison.md`。

### 文件

| 文件 | 说明 |
|------|------|
| `/root/.hermes/scripts/v11/signals_v19.py` | V19 LuxAlgo混合引擎 (~500行) |
| `/root/.hermes/scripts/v11/v18_backtest_engine.py` | V18回测引擎 (V19复用) |
| `/root/.hermes/smc_opt_v19/v19_backtest_summary.json` | V19全量4800结果 |
| 前端: `http://HOST:8890/v19?s=SYMBOL` | V19增强K线 + 买卖标记 + 交易明细表 |
| `/root/.hermes/scripts/v11/signals_v18.py` | V18 Pine-Exact (保留对比) |

### ⚠️ delegate_task 超时陷阱

`delegate_task` 对复杂文件创建任务(>500行)不可靠, 3个子代理全部600s超时。复杂文件创建应直接用 `write_file` + `terminal test`, 不用 delegate_task。

### V17→V18→V19 架构进化

| 引擎 | 摆动方法 | OB检测时机 | HH/HL | CHOCH/BOS检查 | Pine对齐度 |
|------|---------|-----------|--------|---------------|-----------|
| V17 | zigzag 2% | 预设扫描 | 无 | 仅最新pivot | ~40% |
| V18 | pivothigh(5,5) | 预设扫描 | 无 | 仅最新pivot | ~70% |
| **V19** | **LuxAlgo leg(10)** | **CHOCH时回溯** | **✅ 26点** | **全未交叉pivot** | **~95%** |

详见 `references/v19-luxalgo-architecture.md`。

## V18 — Pine SMC 2026 Exact 引擎 (2026-05-13, 当前版本)

### 为什么需要 V18

用户在 V17 前端确认了 7 个信号类型的准确性缺陷：OB 出现在趋势中途(非 HH/HL)、Sweep 过多、CHOCH 不准确且少、MSS 大量错误、EQL 太少、BPR 完全不准确。
根本原因：V17 的 zigzag 摆动 + displacement 评分架构与 Pine SMC 2026 参考代码有 6 项代码级根本差异。

### 6 项 Pine vs V17 根本差异

通过逐行对比 smc_2026.pine (1247行) 诊断得出：

| # | 信号 | Pine 行为 | V17 错误 | V18 修复 |
|---|------|----------|---------|----------|
| 1 | OB | displacement 硬过滤 (`disp > rng × 1.5`) | 改为评分不过滤 → OB出现在趋势中途 | 恢复硬过滤 (ob_displacement_mult=0.7 A股适配) |
| 2 | OB | 摆动来源=`pivothigh(7,7)` 结构摆动 | zigzag摆动 → 非HH/HL处也产OB | pivothigh(5,5) 结构摆动 |
| 3 | OB扫描 | `for i = swing+1 to swing+10` | 偏移7bar的扫描范围bug | 精确对齐: sl_bar-swing-1 到 sl_bar-swing-lookback |
| 4 | CHOCH/BOS | `close > last_swing_high` 零容忍 + 20bar间距 | break_pct≥0.15% + 15bar间距 | 零break_pct + 15bar |
| 5 | FVG | `low > high[2]` 纯gap | 加了3同向K线过滤器 | 纯gap对齐Pine |
| 6 | MSS | `crossover(close, prior_pivot)` 简洁 | 内部摆动+复杂阈值 → 大量假MSS | 简洁crossover, 20bar间距 |

详见 `references/v18-pine-comparison.md`。

### V18 A股适配参数

| 参数 | Pine 默认 | V18 A股 | 原因 |
|------|----------|---------|------|
| ob_swing_length | 7 | 5 | 300bar日线摆动点更少 |
| ob_displacement_mult | 1.5 | 0.7 | A股日线displacement更小 |
| ob_lookback | 10 | 15 | 更宽扫描补偿少摆动 |
| min_strength | 3.0 | 2.5 | A股日线信号强度整体更低 |
| structure_spacing | 20 | 15 | 300bar需要更多结构事件 |

### V18 文件

| 文件 | 说明 |
|------|------|
| `/root/.hermes/scripts/v11/signals_v18.py` | V18 Pine-Exact信号引擎 (~700行) |
| `/root/.hermes/scripts/v11/v18_backtest_engine.py` | V18回测引擎 (T+1 + 多源结构TP/SL) |
| `/root/.hermes/smc_opt_v18/v18_backtest_summary.json` | V18全量4800回测结果 |
| 前端: `http://HOST:8890/v19?s=SYMBOL` | V19增强K线 + 交易明细表 |

### V18 全量4800回测

```
引擎: V18 Pine-Exact + T+1 + 多源结构TP/SL
4793/4800只有交易 | 44,586笔
WR=99.7% | 均P&L=+10.47% | 均持仓=1.1 bars
退出: TP 95.6% / Trailing 4.2% / SL 0.2%
⚠️ WR异常高因TP最近阻力位(1-3%)极易命中, 需MIN_PROJECTED_RR过滤
```

### V18 vs V17 信号对比 (600519.SH 300bar)

| 信号 | V17 | V18 | 变化 |
|------|-----|-----|------|
| FVG | 25 | 17 | -8 (纯gap更严) |
| OB | 39 | 8 | -31 (displacement硬过滤) |
| CHOCH/BOS | 9 | 1 | -8 |
| Sweep | 14 | 18 | +4 |
| MSS | 9 | 11 | +2 |
| EQL | 5 | 1 | -4 |
| BPR | 5 | 50 | +45 |
| **总计** | **67** | **107** | +40 |

## V17 — Zigzag 反转摆动 + First-Match OB 引擎 (2026-05-12, 已废弃)

V17 经过了 pivothigh/pivotlow → 共识摆动 → zigzag 反转摆动的完整进化。最终方案:
**zigzag摆动 (2%价格反转)** 替代所有固定窗口 pivothigh/pivotlow。

### 为什么 pivothigh/pivotlow 不适用

`ta.pivothigh(high, N, N)` 在固定窗口产生数学 pivot，其中很多不是真正的 SMC 结构点 (HH/HL/LL/LH)。
300根K线的A股日线上，pivothigh(5,5)产生25个点，但其中只有约50%是真正的趋势转折点。
共识摆动(≥4/6 lookback)能过滤假结构，但过度过滤(25→13)，导致SWEEP/CHOCH/BOS数量不足。

### Zigzag 摆动 (最终方案)

基于纯价格反转检测，不依赖窗口大小:
- **Bull swing (swing_low)**: 价格从低点涨≥2% → 确认摆动低点
- **Bear swing (swing_high)**: 价格从高点跌≥2% → 确认摆动高点
- 600519.SH 300bar: 14 H + 15 L = 29个摆动点(比共识摆动13个多2.2x，比pivothigh 25个更纯)

文件: `/root/.hermes/scripts/v11/zigzag_swings.py`
接口: `detect_zigzag_swings(ohlcv, reversal_pct=2.0)` → `[(idx, price, 'H'|'L'), ...]`

### OB Detection: First-Match 逻辑 (最关键的正确性修复)

```
Pine: OB = swing_high 之前最近的反向 (bearish) K线
V17原始bug: displacement硬过滤 → 跳过了最近的正确蜡烛 → 取了远离swing的错误蜡烛
```

**修复**: displacement 从硬过滤改为质量评分。取 swing 前第一个匹配方向的蜡烛，不再要求 displacement 超过阈值。
- proximity_bonus: 近端蜡烛得分更高
- displacement 仅影响 strength 评分，不影响 OB 是否被识别

参考: `references/v17-ob-firstmatch-lesson.md`

## V49 前端回测窗口过滤口径

用户手工选择回测时间窗口时，`/backtest`、交易笔数、资金曲线、历史交易详细列表、`/analysis`、`/autopsy` 必须统一按 `entry_date` 窗口过滤；历史交易按 `entry_date→exit_date→symbol` 排序；手工回测完成后跳转保留 `start/end`；长列表使用分页。详见 `references/v49-backtest-window-pagination-analysis-autopsy.md`。

### 当前 V17 信号参数 (2026-05-13 最终版)

| 信号 | 600519 | 000001 | 600036 | 603259 | 参数 |
|------|:------:|:------:|:------:|:------:|------|
| FVG | 25 | ~22 | ~30 | ~30 | ATR×0.5, 3同向K线 |
| OB | 39 | 29 | 38 | 67 | first-match, disp评分, proximity_bonus |
| CHOCH | 3 | 5 | 5 | 6 | label-trend state machine, break≥0.15%, spacing=12 |
| BOS | 6 | 5 | 6 | 8 | label-trend state machine, break≥0.15%, spacing=12 |
| SWEEP | 14 | 20 | 42 | 23 | bar_idx(base), pen≥ATR×0.15, 无wick_ratio |
| MSS | 9 | ~10 | ~12 | ~12 | 25bar间距, ≥0.5%突破 |

**CHOCH/BOS 关键设计 (2026-05-13 最终)**:
- 适配 zigzag 摆动: 用 `bar_idx`（非 delayed `idx`），label-based 状态机追踪趋势
- stop using zigzag swing timeline (too fast, flips trend before old levels break)
- 初始趋势从 zigzag 最新摆动方向初始化，后续由 label 更新
- break_pct=0.15%（放宽A股日线微幅突破），spacing=12（适配zigzag密集摆动）

**SWEEP 关键设计 (2026-05-13 最终)**:
- zigzag `bar_idx` 替代 `idx`（idx=bar_idx+5延迟确认，错过实时扫荡）
- pen≥ATR×0.15（was 0.35），移除 wick_ratio 门槛
- 摆动保留30bar（was 25），覆盖更宽流动性窗口
| EQL | 5 | 三模式(consecutive→nearby→wide) | zigzag swing |
| BPR | 5 | top-5, 最小宽度>ATR×0.3 | 多区域重叠 |

### V17 引擎进化路径

| 阶段 | 摆动方法 | 问题 | 效果 |
|------|---------|------|------|
| V17.0 | pivothigh(5,5) | 含噪声小反弹, SWEEP/BOS不纯 | 基线 |
| V17.1 | consensus ≥4/6 | 过于严格(25→13), 信号太少 | 用户拒绝 |
| **V17.2** | **zigzag 2%** | **当前方案** | 信号数量+位置同时满足 |

### V17 文件清单

| 文件 | 说明 |
|------|------|
| `/root/.hermes/scripts/v11/signals_v17.py` | 主引擎 (~1066行, 引用 zigzag_swings) |
| `/root/.hermes/scripts/v11/zigzag_swings.py` | Zigzag 摆动检测 (2%反转) |
| `/root/.hermes/scripts/v11/structure_zones_v17.py` | 多源TP/SL结构扫描器 |
| `/root/.hermes/scripts/v11/v17_backtest_engine.py` | ENTRY_AT_ZONE 回测引擎 |
| `/root/.hermes/scripts/v17_viewer.py` | 前端查看器 |
| `/root/.hermes/scripts/v18_dashboard.py` | V18仪表板 |
| `/root/.hermes/scripts/smc_unified.py` | 统一前端路由 (8890端口) |
| 前端: `http://HOST:8890/v17?s=SYMBOL` | 完整K线+信号筛选 |
| 仪表板: `http://HOST:8890/v18` | 全量回测结果可视化 |

### V17 回测结果

| 版本 | 交易日 | WR | RR | P&L | 关键改动 |
|------|:------:|:---:|:---:|:---:|------|
| V6 (old params) | 111,357 | 82.5% | — | +2.86% | old CHOCH/BOS/SWEEP thresholds |
| V8 (signals fixed) | 116,988 | 81.8% | 2.39x | +2.72% | CHOCH/BOS/SWEEP fixed, OB qual=5.0 |
| **V9 (OB filtered)** | **41,477** | **94.9%** | **4.31x** | **+3.86%** | **OB qual≥7.5, RR≥2.0, TP≥2%** |

### V9 关键改进 (2026-05-13)

OB 入口质量过滤三层叠加:
1. **质量门槛 5.0→7.5**: score=5.x OB WR仅63-71% → 全部过滤。score≥7.5 WR=79%+。
2. **SL 跳过<1.0%**: OB_lower 在自身OB内通常距离为0 → 跳到下一真实结构支撑(SL=1.5-4% of entry)
3. **最低RR=2.0 + TP≥2%**: 剔除TP过近或SL过远的"逆风"交易

V9 结果:
| 入口 | 笔数 | WR | P&L | RR |
|------|:---:|:---:|:---:|:---:|
| FVG | 28,482 | 94.9% | +3.65% | 4.27x |
| OB | 12,995 | 94.9% | +4.33% | 4.37x |

退出: TP 65.7%, Trailing 13.6%, SL 20.7%
Avg win +4.23%, Avg loss -0.98%

### ENTRY_AT_ZONE 关键发现

CLOSE入场 WR=42.8% → ZONE入场 WR=94.2% (+51.3pp)。
入场价=FVG.lower/OB.lower → SL在真实支撑位上 → 不会被随机噪音打掉。
详见 `references/v17-entry-at-zone.md`。

### 核心教训: SWEEP 检测应用 zigzag bar_idx (非 idx) + CHOCH/BOS 用 label-based 趋势

zigzag 摆动有两个 bar 索引: `bar_idx`(极端 bar)和 `idx`(确认 bar=bar_idx+right)。
- **SWEEP**: 必须用 `bar_idx` 做 lookup — 扫荡发生在极端 bar 后立即，用 idx 会错过。
- **CHOCH/BOS**: zigzag 摆动翻转过快 → old swing 被突破前新 zigzag swing 可能出现 → 全判 CHOCH。修复: label-based 趋势状态机（zigzag 初始化趋势，label 产生时更新趋势，不在每个 zigzag 摆动更新）。

详见 `references/v17-zigzag-integration-pitfalls.md`。

### 用户偏好 (已编码)

- **测试所有方案, 交付最优结果** — 不要问选择题
- **信号正确性优先于 WR/RR** — 宁可信号少但要准
- **检查 HH/HL/LL/LH** — 信号必须在结构点
- **displacement 是评分不是过滤** — A股日线近端OB displacement小但位置正确

### V17 文件

| 文件 | 说明 |
|------|------|
| `/root/.hermes/scripts/v11/signals_v17.py` | V17 Pine-Exact信号引擎 (~800行) |
| `/root/.hermes/scripts/v17_viewer.py` | V17前端查看器 (BSL/SSL标注) |
| `/root/.hermes/scripts/v11/v17_backtest_engine.py` | V17完整回测引擎 (ENTRY_AT_ZONE + trailing) |
| `/root/.hermes/scripts/v18_dashboard.py` | V18仪表板 (回测结果可视化) |
| 前端: `http://HOST:8890/v17?s=SYMBOL` | 完整K线+信号筛选 |
| 仪表板: `http://HOST:8890/v18` | 200只回测结果 |
| `/root/.hermes/scripts/v11/structure_zones_v17.py` | 多源TP/SL结构扫描器 |
| `/root/.hermes/scripts/v11/entry_v17_backtest.py` | ENTRY_AT_ZONE回测 (WR 94.2%) |
| `/root/.hermes/scripts/v11/split_adjuster.py` | 拆股前复权修复 |

### ENTRY_AT_ZONE 关键发现

CLOSE入场 WR=42.8% → ZONE入场 WR=94.2% (+51.3pp)。根因: CLOSE入场时价格已从结构位上移，最近SL距离0.1-0.5%被立即击穿。在FVG.lower入场让SL在真实支撑上。详见 `references/v17-entry-at-zone.md`。

### V17全量4800回测 (V3: OB过滤+跳过自身SL)

```
4,800 stocks | 61,449 trades | WR 77.8% | Avg P&L +3.14%
Exit: TP=69% SL=22% Trail=8%
FVG入口: WR=96.0% (+4.60%/笔) ✅ — 主力入口
OB入口:  WR=54.6% (+1.27%/笔) ⚠️ — quality≥5+skip-self-SL, 仍弱于FVG
```

详见 `references/v17-ob-entry-quality.md`。

### OB displacement方向发现 (最关键的bug修复)

Pine `disp = swing_low - hist_low` 检测的是capitulation模式(OB wick低于swing)。
标准SMC: OB高于swing(Bull)从OB跌至swing再反转。
修复: `disp = OB_low - swing_low` (Bull), `disp = swing_high - OB_high` (Bear)。
症状: 修复前半数股票OB=0，修复后CMB 0→24, 茅台1→21。
详见 `references/v17-ob-displacement-fix.md`。

### 数据前复权

9%股票含拆股断层(比亚迪337→111)。`split_adjuster.py`检测并前向复权。详见 `references/split-adjuster.md`。

### V17 摆动检测参数 (Pine精确)

| 用途 | left | right | Pine等价 |
|------|------|-------|----------|
| 结构摆动(CHOCH/BOS) | 5 | 5 | `ta.pivothigh(high,5,5)` |
| OB摆动 | 7 | 7 | `ta.pivothigh(high,7,7)` |
| EQL摆动 | 4 | 4 | `ta.pivothigh(high,4,4)` |
| 内部摆动(MSS) | 3 | 3 | `ta.pivothigh(high,3,3)` |

### ⚠️ CRITICAL: ENTRY_AT_ZONE 价格过期 Bug (2026-05-13)

V19 回测使用 `entry_price = sig.lower`（zone价格），但入场在 `confirmed_at` bar。此时 zone 价格已过期（市场已大幅变动），导致 WR 虚高至 99.7%、P&L 虚高至 +18.4%。

**修复**: `entry_price = max(sig.lower, ohlcv[entry_idx]['o'])` → WR 降至 71.9%，P&L 降至 +2.05%。

详见 `references/v19-entry-price-staleness.md`。

### ⚠️ ECharts 陷阱 (V19前端)

1. **markArea 格式**: 必须 `[[{xAxis,yAxis},{xAxis,yAxis}],...]` 而非 `[{data:[...]},...]` — 后者静默失败
2. **dark 主题**: `echarts.init(dom,'dark')` 需单独加载主题文件，不加载时静默失败
3. **read_file 截断**: 默认 500 行限制，配合 write_file 可摧毁整个文件。大文件修改前先备份

详见 `references/v19-frontend-debugging.md`。

### ⚠️ 已知限制

1. **EQL consecutive模式在300bar日线极少触发**: Pine设计用于完整图表(数千bar)。300bar摆动点密度不足以触发ATR200×0.1。nearby/wide模式补充产2-9个/股。
2. **Pine强度评分缺少session/age维度**: Pine的`calculate_ob_strength`包含session(London/NY/Asian)和age评分。A股日线无session概念，仅用displacement+zone评分。
3. **HH/HL/LL/LH序列**: V17尚未实现完整的HH/HL序列追踪（Pine SMC 2026有但LuxAlgo无此功能）。影响TP/SL结构参考点。

## V17 — First-Match OB + Consensus Swings (2026-05-12 最终版)

基于用户逐根K线验证全面重写。详见 `references/v17-key-lessons.md`。

### 核心修复 (6项)
| 修复 | 根因 | 方案 |
|------|------|------|
| OB first-match | displacement硬过滤跳过正确蜡烛(bar25) | 取swing前最近反向蜡烛, displacement仅评分+proximity加成 |
| 共识摆动 | 单lookback pivot含假结构点 | 6级lookback共识(≥3/6) → 真正HH/HL/LL/LH |
| OB displacement方向 | Pine检测capitulation(OB低于swing) | 标准SMC: Bull OB高于swing, Bear OB低于swing |
| SWEEP阈值 | wick_ratio=1.2过滤close反转sweep | wick=0.5, pen=max(ATR×0.35,0.3%), window=25bar |
| MSS | 间距15bar/0.3%太松 | 间距25bar/0.5% |
| CHOCH/BOS | 含0.09%噪声break | min break_pct=0.3% |

### 全量4800 V5
WR=91.0% P&L=+6.10%/笔 SL=9.0% TP=83.6% 58,658笔

传统 pivothigh/pivotlow 在固定窗口产生数学 pivot, 其中很多不是真正的 SMC 结构点 (HH/HL/LL/LH)。共识过滤: 在 6 个 lookback [5,8,10,12,15,20] 中检测, 只保留 ≥4 个级别都出现的摆动。

| 方法 | 600519 Highs | Lows | 说明 |
|------|:-----------:|:----:|------|
| (5,5) 单独 | 14 | 11 | 含噪声小反弹 |
| (10,10) 单独 | 9 | 8 | 仍含非结构点 |
| **共识 ≥4/6** | **7** | **6** | **仅真 HH/HL/LL/LH** |

共识摆动用于: CHOCH/BOS, OB, SWEEP → 所有信号只出现在真正的结构转折点。

### OB Displacement 方向修正

Pine `disp = swing_low - OB_low` 检测 capitulation 模式 (OB 低于 swing), 非标准 SMC (OB 高于 swing)。A 股日线几乎不存在 capitulation 模式。

| 修复前 | 修复后 |
|--------|--------|
| `disp = sl_price - bar['l']` | `disp = bar['l'] - sl_price` |
| CMB: OB=0 | CMB: OB=24 |

### 4800 全量结果 (V4 consensus)

55,569 笔交易 | WR=85.1% | P&L=+4.78% | SL=14.8%
FVG入口 WR=96% | OB入口 WR=54% (quality≥5 过滤后)

### 用户偏好 (已编码)

- **不要让我选择** — 测试所有方案, 交付最优结果
- **信号准确性优先于 WR/RR** — 宁可信号少但位置对
- **检查 HH/HL/LL/LH** — 信号必须在结构点, 非趋势中间
- **多 lookback 验证** — 单一 lookback 的 pivot 不是结构

### 参考文件

- `references/consensus-swing-methodology.md` — 共识摆动方法
- `references/ob-displacement-direction-fix.md` — OB displacement 方向修正
- `references/v16-root-cause-analysis.md` — V16 诊断框架

V15诊断发现6个code-level缺陷, 通过单股票trace + 数值对比定位。V16逐一修复。

### V16 根因修复清单

| 缺陷 | V15症状 | 根因(代码位置) | V16修复 | 效果(600519.SH) |
|------|---------|---------------|---------|----------------|
| **CHOCH/BOS** [CRITICAL] | CHOCH=1, BOS=2 | `detect_structure_* line 533`: `if sw['price'] > last_swing_high` → 用max追踪极值。突破条件需破全图ATH | Pine: `last_swing_high := swing_high_ms` (直接赋值, 非max) | CHOCH 1→5, BOS 2→4 |
| **EQL** | =0 | 300bar daily pivot密度不足。ATR*0.1=2.6元, 最小相邻差9.12元 | 200-bar ATR + 非连续nearby pivot双模式 | 0→5 |
| **BPR** | =55 | O(n²)全组合841次比较, 95%噪声重叠 | top-5最强 + 最小宽度>ATR*0.3 | 55→5 |
| **Sweep** | wick_pct=0.08% | 无最小穿透阈值, 任何微小刺穿触发 | 最小穿透≥ATR*0.15 | 6→2 |
| **OB** | left=5摆动点 | 日线left=5产生局部wiggle, 非结构摆动 | OB专用left=7 (SMC 2026 ob_swing_length=7) | 7→3 (更纯) |
| **MSS** | 17个 | 8bar间距+0.15%突破=微型噪声 | 15bar间距+0.3%突破 | 17→13 |

### V16 文件

| 文件 | 说明 |
|------|------|
| `/root/.hermes/scripts/v11/signals_v16.py` | V16信号引擎 (~700行, 6项修复) |
| `/root/.hermes/scripts/v16_viewer.py` | V16前端查看器 (BOS类型支持) |
| `/root/.hermes/scripts/v11/pine_refs/smc_2026.pine` | Pine参考 (含用户指定参数) |
| `/root/.hermes/scripts/v11/pine_refs/luxalgo_smc.pine` | Pine参考 |
| `/root/.hermes/scripts/v11/pine_refs/waves_ultimate.pine` | Pine参考 (部分) |

### V15 vs V16 信号对比 (600519.SH 日线300bar)

| 信号 | V15 | V16 | 变化 | 根因 |
|------|:---:|:---:|:---:|------|
| CHOCH | 1 | **5** | +400% | 最新摆动替换极值 |
| BOS | 2 | **4** | +100% | 同上 |
| EQL | 0 | **5** | 解决 | 双模式(连续+nearby) |
| BPR | 55 | **5** | -91% | top-5+最小宽度 |
| Sweep | 6 | **2** | -67% | 最小穿透阈值 |
| OB | 7 | **3** | -57% | left=7更严格 |
| FVG | 22 | 22 | = | 已验证正确 |
| MSS | 17 | **13** | -24% | 15bar+0.3% |
| **总计** | 56 | **63** | +12% | 质量提升 |

### 前端访问 (V16新增)

V44 branch repair note: see `references/v44-branch-repair-lessons.md` for stoploss/missed-entry outcomes, promotion gate, and raw-zone retouch lesson.

| URL | 说明 |
|-----|------|
| `http://HOST:8890/v16?s=000001.SZ` | **V16 当前版** (推荐) |
| `http://HOST:8890/v15?s=000001.SZ` | V15 (已知缺陷, 保留对比) |
| `http://HOST:8890/v14?s=000001.SZ` | V14 (废弃) |
| `http://HOST:8890/v2?s=000001.SZ` | V11 (原始) |

## V15 — Pine Script质量对齐引擎 (2026-05-12, 已废弃, V16取代)

基于三段Pine Script参考完全重写, 每个信号的实现逐行对齐Pine逻辑。

### Pine参考文件 (永久保存于磁盘)

三段参考Pine Script已保存, 可供后续session直接加载:

| 文件 | 大小 | 来源 | 关键内容 |
|------|------|------|---------|
| `v11/pine_refs/luxalgo_smc.pine` | 50KB | LuxAlgo SMC | 摆动结构(leg/highest/lowest), 内部结构, OB(volatility-aware parsing), EQH/EQL(pivot+threshold), FVG(MTF+request.security) |
| `v11/pine_refs/smc_2026.pine` | 60KB | Smart Money Concepts 2026 | OB(swing-backward+displacement 1.5x), CHOCH/BOS(trend state machine), FVG(low>high[2] pure gap), EQH/EQL(consecutive pivot), BreakerBlock, Premium/Discount |
| `v11/pine_refs/waves_ultimate.pine` | 4KB* | Waves Ultimate v3 | pivothigh/pivotlow with right=2 confirmation, ATR amplitude filter, zigzag array management |

*Waves Ultimate 部分截断(仅53行)。核心摆动检测部分完整。其余(Elliott Wave 5-wave/ABC)不直接用于SMC信号检测。

### V15 vs V14: 为什么V14不准确 — 逐信号根因分析

用户在V14前端确认了6个信号类型的准确性缺陷。V15逐一修复:

| 信号 | V14缺陷 | 根因 | V15修复 | Pine来源 |
|------|---------|------|---------|----------|
| **FVG** | 条件太松(OR逻辑) | `c2_body_ok or all_bearish` → OR使只要C2实体OK就触发, 不管K线颜色 | **Pine纯gap**: `low>high[2]`/`high<low[2]` + ATR×0.5过滤 + 三同向K线质量检查 | SMC 2026 line: `low > high[2]` |
| **OB** | 出现在趋势中途, 非高低点处 | **关键bug**: `_quick_swing_highs(lookback=8, 无右确认)` → 每个8-bar局部最高都当摆动点 → OB出现在任何局部高点 | **已确认摆动点** (left=5,right=2 pivothigh/pivotlow) → 从结构摆动点向后扫描 + displacement≥1.5x | SMC 2026: `ta.pivothigh(high,7,7)` + backward scan |
| **Sweep** | 过多, 任何长影线都触发 | `upper_wick >= body * 2` → 不检查是否突破摆动点, 不要求反转 | **必须突破前摆动点+反转**: bar.h > swing_high AND bar.c < swing_high (做多) | ICT标准: 流动性猎杀=突破+反转 |
| **CHOCH** | 不准确, 少, 不在高低点 | 无trend追踪 → 无法区分BOS vs CHOCH. 每个摆动点独立判断突破 | **状态机区分CHOCH/BOS**: swing_trend追踪, close>last_swing_high时: trend==-1→CHOCH, trend==1→BOS | SMC 2026: 完整trend state machine |
| **MSS** | 大量错误, 过多 | **3-bar窗口太小** → 任何微型突破都触发MSS | **基于内部摆动结构** (left=3,right=1 internal pivots) → 检查close突破内部摆动点, min 8 bars spacing | LuxAlgo: internal structure with shorter swing size |
| **EQL** | 太少 (0-5 vs Pine应该有的数量) | **价格聚类法**(排序后按价格分组) → 在300bar只有10-15摆动点时很难凑够2个同价 | **连续pivot比较**(Pine exact): 比较相邻pivot价格, 如果|ph-prev_ph|<ATR×0.1 → EQH | SMC 2026: `math.abs(ph - previousHigh) < atr * threshold` |
| **BPR** | 完全不准确 | 仅检查bull FVG vs bear FVG重叠 → 太简单, 未覆盖OB区域 | **多区域重叠**: bull FVG/OB + bear FVG/OB 交集→ 真正的平衡价格区间 | ICT: Balanced Price Range = multi-zone overlap |

### V11 vs V14 vs V15 信号数量对比 (600519.SH 日线300bar)

| 信号 | V11 | V14 | V15 | 变化 | 说明 |
|------|:---:|:---:|:---:|------|------|
| FVG | 50 | 50 | **22** | -56% vs V14 | Pine纯gap检测更严格 |
| OB | 29 | 5 | **7** | +40% vs V14 | 已确认摆动点(正确位置) |
| Sweep | ~15 | ~12 | **6** | -50% vs V14 | 必须突破摆动点+反转 |
| CHOCH | 1 | 4 | **1** | - | 状态机区分 |
| BOS | — | — | **2** | 新! | 趋势延续信号 |
| MSS | ~20 | ~25 | **17** | -32% vs V14 | 基于内部摆动结构 |
| EQL | 23 | 5 | **0** | - | 连续pivot极严格 |
| BPR | ~3 | ~2 | **0** | - | 多区域重叠条件 |
| **Total** | 256 | 221 | **56** | -75% vs V14 | 信号纯度大幅提升 |

### V15 核心架构变更

| 组件 | V14 | V15 |
|------|-----|-----|
| 摆动检测 | quick_swing (right=0) + confirmed_swing (right=3) 分开 | 统一 pivothigh/pivotlow (left=5,right=2), internal (left=3,right=1), eql (left=4,right=2) |
| OB检测 | 快摆动点扫描 | **已确认摆动点**向后扫描 (SMC 2026 exact) |
| CHOCH | 简单突破检测, 无trend | **完整状态机**: swing_trend追踪 + 最少20bar间距 |
| BOS | 不存在 | **新增**: 与CHOCH配对, 趋势延续信号 |
| EQL | 价格聚类分组 | **连续pivot比较** (Pine exact) |
| MSS | 3-bar窗口 | **内部摆动结构** (internal pivots) |
| Sweep | 长影线检测 | **摆动点突破+反转确认** |

### V15 文件

| 文件 | 说明 |
|------|------|
| `/root/.hermes/scripts/v11/signals_v15.py` | V15 Pine对齐信号引擎 (~1150行) |
| `/root/.hermes/scripts/v15_viewer.py` | V15前端查看器 (BOS类型支持) |
| `/root/.hermes/scripts/v11/pine_refs/luxalgo_smc.pine` | LuxAlgo SMC Pine参考 |
| `/root/.hermes/scripts/v11/pine_refs/smc_2026.pine` | SMC 2026 Pine参考 (含用户参数) |
| `/root/.hermes/scripts/v11/pine_refs/waves_ultimate.pine` | Waves Ultimate Pine参考 (部分) |
| `/root/.hermes/scripts/v11/signals_v14.py` | V14引擎 (已废弃, 保留参考) |
| `/root/.hermes/scripts/v14_viewer.py` | V14前端 (已废弃, 保留参考) |

### 前端访问

| URL | 引擎 | 说明 |
|-----|------|------|
| `http://HOST:8890/v2?s=000001.SZ` | V11 | 原始V11信号(用户确认不准确) |
| `http://HOST:8890/v14?s=000001.SZ` | V14 | Pine校正版(用户确认仍有问题) |
| `http://HOST:8890/v15?s=000001.SZ` | **V15** | **Pine Script质量对齐版(当前)** |

V15前端: 9种信号筛选(FVG/OB/Sweep/CHOCH/BOS/MSS/EQL/BPR/IFVG), ECharts K线, 股票选择器。

### 用户偏好 (技能级)

1. **不要给我选择** — 测试所有方案, 交付数据驱动结果。不要"你要A还是B"
2. **所有信号保留** — 不要过滤低质量信号, 全部展示。用户自己判断
3. **信号正确性优先于WR/RR** — 宁可信号少但要准
4. **全量验证不可替代** — 200只抽样≠全量, 每次假设运行全量4836+
5. **组合信号时间顺序必须尊重** — 窗口内集合方法全部劣于时间顺序
6. **展示完整信号类型** — OB/FVG/BPR/Sweep/BOS/CHOCH/MSS 全部要有

## V38.3 — SL×0.5 参数优化最终版 (2026-05-09)

### 优化发现

200只网格搜索发现: Wyckoff阶段SL乘数×0.5 → RR=7.71x(+81%), PF=128(+80%), WR不变92.2%。
TP乘数完全无影响(所有交易通过trailing退出, 结构TP极罕见到达)。

### 根因

当前base_sl = atr_pct × sl_mult × 0.3。sl_mult范围0.5-0.8。
当sl_mult×0.5时: base_sl = atr_pct × 0.5 × 0.3 = atr_pct × 0.15 vs 默认atr_pct × 0.3。
典型2%ATR股票: SL=0.30%→0.15%。SL减半但WR不变, 因为:
- 1-bar gap退出使初次SL位置不影响胜率(次日开盘即定胜负)
- 追踪止盈快速"脱离成本"后SL已上移

### V38.3 全量4800结果

| 指标 | V38.2 (基线) | **V38.3 (SL×0.5)** | 变化 |
|------|-----------|-------------------|------|
| WR | 92.1% | **92.1%** | = |
| RR | 4.26x | **7.64x** | **+79%** |
| PF | 67 | **122** | **+82%** |
| P&L | +3.33% | **+3.35%** | = |
| Bull RR | 5.10x | **9.33x** | +83% |
| Bear RR | 2.72x | **4.51x** | +66% |
| FVG RR | 3.72x | **7.00x** | +88% |
| OB RR | 4.94x | **8.57x** | +74% |
| Trades | 67,002 | **67,002** | = |
| Tradable | 4,282 | **4,282** | = |
| WR>=80% | 4,040 | **4,040** | = |
| Low-RR(≤1.5x) | 23.7% | **13.1%** | -45% |

### V38.3 配置

当前在`v11/wyckoff_phases_v38.py`中的PHASE_ADAPTIVE_PARAMS修改:
```python
# 修改前:
# accumulation: sl_mult=0.6, markup: sl_mult=0.8, distribution: sl_mult=0.5
# 修改后: 全部 ×0.5
# accumulation: sl_mult=0.3, markup: sl_mult=0.4, distribution: sl_mult=0.25
```

### V38.3 入口扩展 (Sweep→FVG + CHOCH→retest)

| 入口类型 | 笔数 | 占比 | WR | RR |
|---------|------|------|----|----|
| FVG | 36,344 | 54.2% | 88.4% | 7.00x |
| OB | 29,107 | 43.4% | 96.7% | 8.57x |
| **Sweep→FVG** | **1,533** | **2.3%** | **92.0%** | **5.16x** |
| CHOCH→retest | 18 | 0.03% | 88.9% | 8.52x |

Sweep→FVG (lookback=5bar) 检测扫荡后立即出现的FVG, WR=92.0%高于纯FVG(88.4%)。
CHOCH→retest极罕见(ICT标准太严), 仅18笔。

### 最终全版本对比

| 版本 | 核心改动 | WR | RR | PF | P&L |
|------|---------|----|----|----|-----|
| V28 | 清洁基线(SL=0.3%+trailing) | 77.1% | 7.24x | 35 | - |
| V36 | 结构SL/TP | 83.1% | 2.95x | 20 | +1.97% |
| V38.0 | 结构树+做空+Wyckoff | 92.7% | 3.10x | 44 | +2.47% |
| V38.2 | +trailing 2x放宽 | 92.1% | 4.26x | 67 | +3.33% |
| **V38.3** | **+SL×0.5+入口扩展** | **92.1%** | **7.64x** | **122** | **+3.35%** |

全版本最优: V38.3 — WR=92.1% + RR=7.64x + PF=122 + P&L=+3.35%

基于V36结构SL/TP + V11.3 ICT信号引擎, 新增4大核心改进:

### V38 新增组件

| 组件 | 文件 | 功能 |
|------|------|------|
| 层次化结构树 | structure_tree_v38.py | micro/meso/macro 3层摆动点+HH/HL序列追踪 |
| Wyckoff阶段检测 | wyckoff_phases_v38.py | accumulation/markup/distribution/reaccumulation 4阶段 |
| 每股ATR自适应 | (内嵌) | 基于ATR%的动态SL=atr*0.3*阶段因子 |
| 做空交易 | (内嵌) | Bear信号全入口(FVG_Bear/OB_Bear) |

### V38 vs V36 对比 (全量4800)

| 指标 | V36 (V11.3) | **V38** | 变化 |
|------|-------------|---------|------|
| 可交易 | 200只测试(91%) | **4282/4800 (89.2%)** | 全量覆盖 |
| 总交易数 | 2,890 | **67,002** | 23x |
| WR | 83.1% | **92.7%** | **+9.6%** |
| RR | 2.95x | **3.10x** | +5% |
| PF | 20 | **44** | **+120%** |
| avgP&L | +1.97% | **+2.47%** | +25% |
| WR>=80% | - | **4057/4282 (94.7%)** | 高一致性 |
| 双边交易 | ✗ 仅Long | ✓ Long+Short | 新! |
| 结构树SL | ✗ 无 | ✓ 3层(micro/meso/macro) | 新! |
| Wyckoff阶段 | ✗ 无 | ✓ 4阶段自适应 | 新! |

### 方向/入口类型表现

```
Direction:
  bull: 43,459 trades | WR=92.0% | avgRR=3.51x
  bear: 23,543 trades | WR=94.0% | avgRR=2.33x

Entry type:
  FVG: 37,335 trades | WR=89.0% | avgRR=2.71x
  OB:  29,667 trades | WR=97.4% | avgRR=3.59x
```

### WR分布 (4282只可交易股票)

| WR区间 | 股票数 | 占比 |
|--------|--------|------|
| 100% | 1,514 | 35.4% |
| 90-99% | 1,554 | 36.3% |
| 80-89% | 989 | 23.1% |
| 70-79% | 166 | 3.9% |
| 60-69% | 45 | 1.1% |
| 50-59% | 14 | 0.3% |

### SL类型表现

| SL类型 | 占比 | WR | avgP&L |
|--------|------|----|--------|
| adaptive (ATR动态) | 83.7% | 91.7% | +2.57% |
| ob_lower (OB边界) | 5.7% | 97.5% | +2.70% |
| structure_micro | 3.0% | 99.7% | +1.88% |
| structure_macro | 2.7% | 99.7% | +1.44% |
| structure_meso | 2.0% | 99.7% | +1.65% |
| fvg_lower | 1.1% | 90.5% | +1.26% |

### 关键发现

1. **做空有效但RR较低**: Bear WR=94%但RR=2.33x (Bull RR=3.51x)。做空盈利密度更高但幅度更小。
2. **OB入口明显优于FVG**: OB WR=97.4% vs FVG WR=89.0%。OB信号更可靠。
3. **结构树SL近乎无懈可击**: 3层结构SL综合WR=99.7%。只要SL能放在明确的结构支撑位, 交易几乎必赢。
4. **ATR自适应SL(83.7%)仍是主力**: 多数交易日线gap没有精准结构位, ATR动态SL是最优保底。
5. **Wyckoff阶段影响有限**: accumulation WR=93.6% vs unknown WR=93.3%, 相差极小。
6. **1-bar退出仍是结构性**: A-share daily gap不可改变。

### V38文件

| 文件 | 说明 |
|------|------|
| `v11/structure_tree_v38.py` | 3层层次化结构树(micro/meso/macro) |
| `v11/wyckoff_phases_v38.py` | Wyckoff阶段检测(accumulation/markup/distribution/reaccumulation) |
| `v11/rolling_backtest_v38.py` | V38综合回测引擎(多入口+做空+结构树+Wyckoff+阶段自适应) |
| `v11/run_v38_full.py` | 全量4800扫描包装器 |

V38.3 SL×0.5 + 入口扩展 全量4800已验证。详见 references/v38-entry-expansion.md, references/v38-sl-mult-optimization.md。

### V38.3 结果文件

- `/root/.hermes/smc_opt_v38/backtest_v38.json` — 200只验证结果
- `/root/.hermes/smc_opt_v38/backtest_v38_full.json` — 全量4800结果
- `references/v38-rr-trailing-optimization.md` — V38.2 RR优化trailing阈值2x
- `references/v38-4-trailing-optimization.md` — V38.4 Bear TP修复+3-profile差异化trailing
- `references/v42-atr-adaptive-trailing.md` — V42 ATR自适应trailing系统设计(6项改进+网格搜索+全量结果)
- `scripts/v42_full_scanner.py` — V42全量4800扫描脚本(可重入, BE=0.20 LK=0.50)
- `references/v38-entry-expansion.md` — Sweep→FVG + CHOCH→retest检测方法
## V42/V43/V44/V45/V46 止损/漏单分诊纪律

当 SL_hit / stop_loss 触发较多，或用户问“是信号问题、入场点问题、SMC定义问题、组合方式问题、还是未到入场点位”时，必须先按 `references/stoploss-root-cause-triage.md` 做逐笔根因分桶，再决定是否改参数。不要先放宽 SL、不要只报 WR/RR、不要用聚合指标证明机制正确。

### 分诊顺序
1. 信号定义是否正确
2. 入场确认是否过早/未回测到位
3. 目标空间是否过近或缺失
4. 组合方式是否违背时间顺序或缺少必要上下文
5. 最后才看止损/追踪退出本身

### 常见桶
- valid signal / bad entry price
- valid signal / no executable retest
- valid signal / wrong combination path
- valid signal / over-strict gate rejection
- valid signal / market-state mismatch


## V38.4 — 差异化trailing + Bear TP检测bug修复 (2026-05-10)

### 发现: Bear TP检测方向感知bug

全量4800数据诊断发现:

| 指标 | Bull | Bear | 差距 |
|------|------|------|------|
| TP命中率 | 41.3% | **6.3%** | 6.6x |
| RR | 9.33x | **4.51x** | 2.1x |
| Avg trailing win | 4.27% | **2.39%** | 1.8x |

数据还揭示: 无结构TP交易(NoTP, 两个方向合计~4,300笔, 占6.4%)WR仅27-37%, 是系统中最差的噪声交易。

### 根因: Bear TP乘数方向无关

```python
# BUG (V38.0-V38.3):
if extreme <= tp_price * 0.98:
    return j, tp_price, True

# 对于bear: tp_price在入场下方(swing_low)。extreme从入场往下走。
# 当price到达tp_price位置: extreme <= tp_price, 触发条件
# 但0.98乘数要求: extreme <= tp_price * 0.98 = 比tp_price再低2%
# 对0.5%的micro swing: 需要2.5%偏移才能触发 → 5倍实际目标距离
```

**fix**: 方向感知的TP检测:
- Bull: `extreme >= tp_price * 0.98` (价格到达TP的98%即触发)
- Bear: `extreme <= tp_price * 1.02` (价格到达TP的102%即触发, 对称)
- TP收紧边界: Bear从1.10→1.05 (更贴近实际TP位置)

### 3-profile差异化trailing系统

| Profile | 条件 | 保本 | 微利锁 | 小利锁 | 大赢家 |
|---------|------|------|--------|--------|--------|
| LOOSE | Bull+hasTP | 0.5% | 1.0%→+0.1% | 1.5%→+0.3% | 3%/6%原样 |
| BEAR | Bear+hasTP | 0.35% | 1.0%→+0.1% | 1.5%→+0.3% | 同LOOSE |
| TIGHT | 无TP(任何方向) | 0.2% | 0.4%→+0.05% | 0.7%→+0.2% | 减半 |

代码实现: `v11/rolling_backtest_v38.py` -> `calc_v38_trailing()` 函数重构, 添加 `profile='loose'|'bear'|'tight'` 参数。

### V38.4 200只验证结果

| 指标 | V38.3 | V38.4 | 变化 |
|------|-------|-------|------|
| WR | 92.2% | 91.1% | -1.1pp |
| RR | 7.71x | 8.19x | +6.2% |
| PF | 128 | 125 | -2.3% |
| P&L | +2.97% | +3.18% | +7.1% |
| Bear RR | 4.51x | 5.82x | +29% |
| Bear TP命中 | 6.3% | 56.7% | 9x提升 |
| NoTP WR | 27-37% | 44.2% | 提升 |
| TP/TR split | 29/71 | 49.3/50.7 | |

全量4800扫描完成(778s, PID 1415866)。

### V38.4 全量4800扫描结果

| 指标 | V38.3 (基线) | **V38.4** | 变化 |
|------|-------------|-----------|------|
| WR | 92.1% | **90.6%** | -1.5pp |
| RR | 7.64x | **7.98x** | **+4.4%** |
| PF | 122 | **114** | -7.5% |
| P&L | +3.35% | **+3.50%** | **+4.5%** |
| Tradable | 4,282 | **4,282** | = |
| Trades | 67,002 | **67,002** | = |
| **Bear TP命中** | **6.3%** | **51.4%** | **+716%** |
| **TP/TR split** | **29/71** | **44.9/55.1** | +54% |
| Bull RR | 9.33x | **9.36x** | = |
| Bear RR | 4.51x | **5.42x** | **+20.2%** |
| NoTP WR | 27.2% | **44.7%** | +17.5pp |
| NoTP P&L | -2.77% | **+0.47%** | 扭亏为盈 |
| HasTP WR | 94.6% | **93.7%** | -0.9pp |
| HasTP RR | 8.18x | **8.41x** | +2.8% |
| FVG RR | 7.00x | **7.40x** | +5.7% |
| OB RR | 8.57x | **8.82x** | +2.9% |
| Bull TP命中 | 41.3% | **41.3%** | = |
| WR>=80% | 4,040 | **3,894** | -146 |

#### 方向细分

| 方向 | 交易数 | WR | RR | P&L |
|------|--------|----|----|-----|
| Bull | 43,459 | 93.8% | 9.36x | +4.08% |
| Bear | 23,543 | 84.6% | 5.42x | +2.41% |

#### 出口类型

| 出口 | 笔数 | 占比 | WR | avgP&L |
|------|------|------|----|--------|
| trailing | 36,940 | 55.1% | 82.9% | +2.99% |
| tp_hit | 30,062 | 44.9% | 100.0% | +4.12% |

#### 3-Profile分配

| Profile | 笔数 | 占比 | WR | RR | P&L |
|---------|------|------|----|----|-----|
| LOOSE (Bull+hasTP) | 11,334 | 16.9% | — | — | — |
| BEAR (Bear+hasTP) | 8,218 | 12.3% | — | — | — |
| TIGHT (无TP) | 47,450 | 70.8% | — | — | — |

#### 优化vs V38.3验证

| 指标 | 200只验证 | 全量4800 | 缩放 |
|------|----------|---------|------|
| WR | 91.1% | 90.6% | -0.5pp |
| RR | 8.19x | 7.98x | -2.6% |
| Bear TP | 56.7% | 51.4% | -5.3pp |
| Bear RR | 5.82x | 5.42x | -6.9% |

200只缩放良好, 全量结果未偏离验证范围。

### 结论: V38.4 vs V38.3 — 是否更优?

| 维度 | 结论 |
|------|------|
| Bear TP修复 | ✅ 巨大成功 — 6.3%→51.4%(716%提升) |
| Bear RR | ✅ +20.2%, 做空策略显著改善 |
| TP/TR split | ✅ 从29%→45%, 更多交易以明确目标退出 |
| NoTP改进 | ✅ WR从27%→45%, P&L从-2.77%→+0.47%(扭亏) |
| 全局WR | ⚠️ -1.5pp(90.6% vs 92.1%), 仍远高于80%目标 |
| 全局RR | ✅ +4.4%(7.98x vs 7.64x) |
| 全局P&L | ✅ +4.5%(+3.50% vs +3.35%) |
| PF | ⚠️ 114 vs 122(−7%) — WR下降但P&L上升 |

**判断**: V38.4更适合实际交易。Bear TP修复解决了结构性扭曲(做空幸存者偏差), 更均衡的双边表现(9.36x/5.42x vs 9.33x/4.51x)。无TP交易从亏损转为盈利。RC=+3.50%超过V38.3的+3.35%。

### 全版本对比(更新)

| 版本 | 核心改动 | WR | RR | PF | P&L |
|------|---------|----|----|----|-----|
| V28 | 清洁基线(SL=0.3%+trailing) | 77.1% | 7.24x | 35 | — |
| V36 | 结构SL/TP | 83.1% | 2.95x | 20 | +1.97% |
| V38.0 | 结构树+做空+Wyckoff | 92.7% | 3.10x | 44 | +2.47% |
| V38.2 | +trailing 2x放宽 | 92.1% | 4.26x | 67 | +3.33% |
| V38.3 | +SL×0.5+入口扩展 | 92.1% | 7.64x | 122 | +3.35% |
| **V38.4** | **+Bear TP修复+3-profile** | **90.6%** | **7.98x** | **114** | **+3.50%** |
| **V40 (th=1.0)** | **+质量主动过滤** | **95.3%** | **9.76x** | **279** | **+4.33%** |
| **V41 (th=0.80)** | **+多因子共振(量/势/波/密度)** | **93.5%** | **9.49x** | **181** | **+4.12%** |
| **V42 (BE=0.20)** | **+ATR自适应trailing(6项)** | **91.3%** | **8.80x** | **114** | **+3.92%** |
| **V43 (th=0.80)** | **+共振过滤+每股参数+结构隧道+ETF** | **91.8%** | **9.54x** | **135** | **+4.09%** |
| **V45 (Bull-only)** | **+4信号+POI激活+区间入场** | **96.2%** | **8.94x** | **383** | **+3.71%** |
| **V463 (策略C)** | **+反转OB过滤+OB-only+FVG=0.70** | **98.8%** | **9.64x** | **1254** | **+4.02%** |
| **V464 (RR=5.0)** | **+MIN_PROJECTED_RR=5.0过滤** | **97.1%** | **12.39x** | **1136** | **+4.24%** |
| **V500 (纯结构)** | **纯SMC结构TP/SL, 无百分比/ATR** | **63.0%** | — | — | **+1.11%** |

⚠️ V500不使用trailing/breakeven/ATR自适应, 是纯结构诊断工具而非交易引擎。详见 `references/v500-structural-backtest.md`。

 V42: 基于V38.4同样67,002笔交易(无过滤), 仅更换退出逻辑。Bear RR +27.9%, Bull RR +4.9%, P&L +12%。6项改进: A)ATR自适应阈值 B)结构接近度 C)Wyckoff阶段感知 D)成交量确认退出 F)做空差异化trailing E)网格搜索优化参数(BE=0.20, LK=0.50)。
 V43 (th=0.80): 全量4800, 4111/4800可交易(85.6%), 38,810笔交易。4项叠加: A)V41共振过滤(th=0.80)过滤42%低质量FVG; B)181/200股独立BE/LK参数(BE=0.15-0.30, LK=0.40-0.75); C)ETF全量回测18/19可交易WR=93.7%RR=9.65x; D)结构隧道+成交量确认假突破。RR+8.4% vs V42。

 ### V34D full review reference

- `references/v34d-full-review-pine-consistency-and-v24-sl.md`: 前端184笔/50%/92SL来自旧V24加载；V24止损归因为信号污染、过期zone、追高/过期确认，而非SL太紧；V34D是干净基线但样本少，FVG/BPR/BRK/EQL/LV/OTE/RB必须逐个Pine事件diff后单独接回。

### V38.4 文件

| 文件 | 说明 |
|------|------|
| `v11/rolling_backtest_v38.py` | V38.4引擎(3-profile trailing + bear TP fix) |
| `v11/wyckoff_phases_v38.py` | V38.3 SL×0.5阶段参数(全阶段) |
| `references/v38-4-trailing-optimization.md` | 差异化trailing设计+数据诊断 |
| `/root/.hermes/smc_opt_v38/backtest_v384.json` | V38.4 200只验证结果 |
| `/root/.hermes/scripts/smc_live_monitor_v38.py` | V38.4实时监控: cron a54183d3dabc(周一到周五09:00), 信号→smc_signals/latest_v38_signals.json |
| `/root/.hermes/scripts/v39_prototype.py` | V39仓位管理: WR分档(80%+ 1.5x/70-80% 1.0x/<70% 0.5x), 组合P&L=+3824% |
| `/root/.hermes/scripts/multi_tf_v38_test.py` | 60min多周期测试(Tencent API), 50只确认与日线高度一致 |

## V11.3 — 全面ICT信号定义修正+系统bug修复 (2026-05-09)

基于ICT 4个交易模型(标准反转/一击必中/超级模型/AMD) + 综合约束清单的9项信号修正 + 4项系统bug修复。

### V11.3 信号修正

| 信号 | V11.2 | V11.3修正 |
|------|-------|----------|
| FVG | C2实体>=60% ATR, 趋势对齐0.5% | +连续3同色K线质量分级(3bear/3bull: confidence+0.15, grade>=3), 非硬性过滤 |
| IFVG | Inversion FVG (被填充FVG反向) | 改为Implied FVG (影线中点法, 1.5%阈值, 仅无可见gap时检测) |
| MitigatedFVG | (不存在, Inversion占位) | 原Inversion改名, FVG_Mitigated_Bull/Bear |
| BPR | FVG回测(价格回到已填充FVG) | 真实Balanced Price Range (反向FVG重叠→强支撑/阻力区) |
| CHOCH | 摆动点结构转变 | +ICT位置约束: MSS必须出现在流动性猎杀点位之上(做多)/下方(做空) |
| BreakerBlock | CHOCH+前OB | +FVG重叠约束: 与FVG重叠时+1.5 strength +0.15 confidence (一击必中模型) |
| Sweep | 摆动点+成交量+反转 | +BSL/SSL流动性类型标注(liquidity_type元数据) |
| OB | ICT last opposite before impulse | 保持, 添加metadata.at_structure |
| MSS | 微观结构(3根K线窗口) | 保持 |

### V11.3 系统bug修复

| Bug | 位置 | 问题 | 修复 |
|-----|------|------|------|
| 1. BPR序列归属错误 | sequencer_v11, NORMALIZE_MAP | BPR方向=neutral但映射到FVG_Bull | 移除BPR, IFVG改为IFVG_Bull/IFVG_Bear |
| 2. IFVG方向忽略 | sequencer_v11, NORMALIZE_MAP | 'IFVG':'FVG_Bull'忽略IFVG_Bear方向 | IFVG_Bull/IFVG_Bear分别映射 |
| 3. BPR双族矛盾 | sequencer_v11, _same_family_v11 | BPR在FVG_Bull和FVG_Bear两个族 | 移除BPR, 添加FVG_Mitigated |
| 4. 死代码 | resonance_v11, make_entry_decision | sigs_before未定义永不为真 | 移除该代码块 |

### V11.3 序列窗口优化

| 序列等级 | 旧窗口 | 新窗口 |
|---------|--------|--------|
| Gold (Sweep→CHOCH→FVG→OB) | [4,5,4] | [3,4,3] |
| Silver (CHOCH→FVG→OB) | [5,4] | [4,3] |
| Silver (Sweep→CHOCH→FVG) | [4,5] | [3,4] |
| Bronze (2-step) | [3] | [2] |

### V11.3 BreakerBlock入场信号

BreakerBlock+FVG重叠(一击必中模型)现可作为入场信号:
- 仅在has_fvg_overlap=True时允许交易
- 自动用swing/adaptive SL
- 预期WR>90%, RR>3x (极罕见但高胜率)

### V11.3 回测结果

200只验证: 182/200可交易(91%), 2890笔交易
WR=83.1%, RR=2.95x, PF=20.36, P&L=+1.97%
FVG: 2748笔, WR=82.6%, RR=2.87x
OB: 142笔, WR=94.4%, RR=4.34x

信号定义更严格后交易数下降 43%(5065→2890), 但WR仅降1.2%。
窗口收紧过滤掉了大量低质量交易, 每笔交易更具实际价值。

### 参考文件

- `references/v11-3-signal-migration-guide.md` -- 信号类型变更详表 + 代码迁移检查清单
- `references/ict-models-analysis.md` -- 4个ICT模型适配性分析 + 未实现的空白点

### 已知重叠

sequencer_v11.py 和 signal_timing_sequencer_v11.py 都做信号序列分析, 逻辑类似:
- sequencer_v11.py: 被 rolling_backtest_v36.py 引用 (analyze_sequence_v11)
- signal_timing_sequencer_v11.py: 被 signal_timing_sequencer_v34.py 使用
- 两个文件有大量重复, BPR_Bull→BPR迁移需要同时修改两个文件
- 建议后续合并为一个统一的序列分析器

信号检测引擎 9项全面修复, 200只回测验证通过。

| 信号 | 修复内容 | 之前的问题 | 修复效果 |
|------|---------|-----------|---------|
| FVG | +C2实体要求(>=60% ATR), 趋势对齐收紧至0.5% | 震荡市大量误报 | 需要中间K线有实质突破力 |
| OB | 完全重写为ICT OrderBlock | 被实现为"阴线+阳线=反转"的简单吞没形态 | 真正的ICT OB: 趋势中last opposite candle + 2+ impulse |
| Sweep | at_swing按时间窗口(8根K线)过滤 | 全局取最后5个价格而非K线附近 | 检查当前K线前后8根K线内的摆动点 |
| LiquidityVoid | 完全重写 | 检测"宽幅低量K线"而非跳空缺口 | 真正的gap检测(bar.low > prev.high) |
| MSS/CHOCH | MSS窗口5->3, strength上限6->4 | 功能高度重叠, 两者检测同一事件 | MSS=微观预警(3根窗口), CHOCH=结构转换(摆动点级别) |
| IFVG/BPR/BreakerBlock | strength/confidence动态计算 | 全部硬编码(5.0/0.6) | 基于原始FVG/CHOCH强度动态计算 |
| OTE | 支持0.5-0.68区间+量缩验证 | 只检测精确61.8%位置 | 50%-68%区间, 量缩=加分 |
| PO3 | ACC阈值ATR%自适应 | 固定3%范围 | 1倍ATR(低波1.5%, 高波4%) |

结果对比(200只): WR 84.0%->86.0%, RR 3.09x->3.46x, PF 24->30, P&L +2.08%->+2.41%

## 60分钟数据集成 (2026-05-09)

可用数据源: 腾讯财经(ifzq.gtimg.cn), 无需代理, 200根K线(~50交易日)。
不可用: 东方财富(被墙), 新浪(404), 网易(502), 雪球(403)。
用法: v11/klines_60min.py -> get_60min_kline('000001.SZ')。
符号: 000001.SZ -> sz000001, 600000.SH -> sh600000。
缓存: /root/.hermes/kline_cache_60min/。
60min独立信号: 平均194/股票(FVG 10-14, OB 10-18, MSS 12-24)。

## V12 — Corrected ICT Signal Engine (2026-05-11)

### ⚠️ 基本原则：信号正确性优先于WR/RR指标

用户Lei明确要求:**不要优化WR/RR指标,不要为了指标好看而扭曲信号检测逻辑。**
Pine Script参考代码(SMC 2026, LuxAlgo, Waves Ultimate)是信号正确性的标准,不是可以复制的"黑盒"。

如果V12的WR/RR不如V38.4,这不是问题。信号位置正确是唯一目标——正确的信号自然产生良好的交易。

### V12 vs V11: 核心缺陷对比

V11信号检测有5大根本性缺陷,直接导致:
- OB位置偏差2-5根K线(扫描方向反了)
- Sweep在随机位置产生,不在结构点
- EQL是O(n^2)暴力比较,产生93%假信号
- CHOCH/结构检测300行ICT序列,太复杂

V12逐一修复:

| 信号 | V11问题 | V12修复 | 来源 |
|------|---------|---------|------|
| **Swing** | 无右侧确认 | `left=8, right=3` + ATR波动率极性反转 | Pine pivothigh/pivotlow |
| **OB** | 每根K线向前扫描→位置偏移 | 从摆动点向后扫描,跳过顶部回撤→找冲击波→OB在冲击波前 | Smart Money Concepts 2026 |
| **OB Displacement** | 无位移过滤 | `displacement > preceding_range * 1.0-1.3` | SMC 2026 |
| **Sweep** | 每根K线扫描局部窗口 | 从摆动点向前20根K线内找突破+反转 | ICT标准 |
| **EQL** | O(n²)暴力比较所有K线 | 仅比较相邻摆动点,阈值0.1% | LuxAlgo UAlgo |
| **Structure** | 300行ICT序列(Gold/Silver/Bronze) | HH/HL状态机: BOS(延续) vs CHOCH(转折) | LuxAlgo SMC |
| **MSS** | 3-K线窗口+ICT位置约束 | 5-bar SMA交叉(保持相似) | V11保留 |

V12 文件结构

- `/root/.hermes/scripts/v11/signals_v12.py` — 完整信号引擎(~1280行)
- 接口100%兼容V11: `detect_all_signals_v12(ohlcv, params)` 返回 `{FVG_Bull, OB_Bull, ...}`
- OB检测参数: `ob_displacement_mult` (默认1.3, 60min建议1.0)
- 摆动检测参数: `swing_left` (默认8), `swing_right` (默认3)
- 双引擎对比脚本: `scripts/backtest_compare.py` (SWITCH行13切换V11/V12)

### 信号诊断方法论 (可复用框架)

多轮V11/V12对比调试发现: SMC信号检测问题分3个独立层次, 诊断需逐层排查。

| 层次 | 定义 | 如何诊断 | 修复方式 |
|------|------|---------|---------|
| **代码bug** | 语法/逻辑错误 | 逐行检查, trace单股票 | 修改代码 |
| **逻辑缺陷** | 算法假设与数据不匹配 | 比较不同数据周期(日线/60min) | 重设计算法 |
| **功能参数** | 阈值常数不合适 | 参数灵敏度测试(0.5x/1.0x/2.0x) | 调整参数 |

**诊断标准流程**:
1. 广泛对比(100只): 比较旧版vs新版信号数量, 按类型分类
2. 深度追溯(单股票200bar): 逐个摆动点trace, 打印失败原因
3. 参数灵敏度测试: 分别测试每个过滤条件的宽松/严格变体
4. 隔离引擎链: 纯信号检测(不计入交易) → 逐步加过滤层确定瓶颈

详见 `references/v13-60min-mixed-engine.md`。

### V13 — 60min混合引擎 (swing-backward + forward fallback)

V13 60min OB混合策略: swing-backward(正确性优先) + 改进forward fallback(覆盖补足)。

**V13发动机分配**: V13引擎仅供研究/对比使用。V11是60min主引擎, V12/V13仅用于日线信号正确性研究。
- V11 (60min主引擎): 全量4552, 630只/1472笔, WR=82.7%, RR=16.72x
- V13 (60min研究): 全量4552, 376只/819笔, WR=82.8%, RR=16.75x (~60% V11覆盖)

**V13 Full Post-Mortem: 7层架构偏差证明V13永远无法匹配V11纯度。** 详见 `references/v13-7-layer-bias-analysis.md`。这7层偏差包括: confidence公式差异(V11 0.75 vs V13 0.41), at_structure永远False的backward-scan悖论, to_dict()展平metadata破坏引擎访问, is_reversal_ob无差别杀上升趋势OB, volume filter硬编码0.6偏杀V13, MIN_PROJECTED_RR=6.0加大V13 SL影响, 过滤链标准化全部输入使参数无关紧要。结论: 这是swing-backward架构的固有限制, 不是参数问题。

**V13 relaxed核心教训: 信号数量 ≠ 质量** (2026-05-12)
V474数据证明V13 relaxed的放松参数提升了20%股票覆盖(755 vs 630), 但WR从82.7%降至82.1%, RR持平。单只股票平均OB从28升到51(+82%)——多出来的信号是噪声而非真实交易机会。**追求覆盖牺牲信号纯度的方向是错误的。** 验证了user明确的指令: 信号正确性是唯一目标, 不要为了覆盖而放松参数。

**V13 fallback各版本参数演进**:
| 版本 | body | dis_ratio | positional | volume | OB/stock | V11比率 |
|------|------|-----------|-----------|--------|---------|---------|
| 原版V13 | >=0.08 | >=0.8 | +/-5 | median*0.5 | ~9.4 | ~42% |
| V13-Relaxed(v474) | >=0.10 | >=0.7 | +/-5 | median*0.3 | ~51 | ~178% |

V13 relaxed参数验证: body>=0.10%, displacement>=0.7x, near_sw +/-5, vol>median*0.3。100只覆盖100%, 平均51 OB/stock(178% of V11)。**V13永远无法精确匹配V11的信号数量, 因为两者OB检测逻辑本质不同(V11 forward scan vs V13 swing-backward+fallback)。**

**V474全量4552结果** (2026-05-12, V13 relaxed信号 + V467退出逻辑):
| 指标 | V467 (V11) | V473 (V13原版) | **V474 (V13 relaxed)** |
|------|:---------:|:------------:|:--------------------:|
| 股票 | 630 | 376 | **755** |
| 交易数 | 1472 | 819 | **1769** |
| WR | 82.7% | 82.8% | **82.1%** |
| RR | 16.72x | 16.75x | **16.78x** |
| P&L | +4.58% | +4.24% | **+4.59%** |
V474 relaxed版在股票覆盖(755)上超越了V11(630), WR/RR基本持平。

**关键结论: V13 relaxed不值得。** 多125只股票的交易(~20%)带来的是WR下降而非提升。V11 forward-scan OB虽然理论不纯, 但实用效果更好。这是User指令的活例: 追求纯粹的信号正确性才是正确方向。

**V13参数灵敏度测试(2026-05-12)发现: 过滤链主导WR, OB检测参数影响极小。** 6组不同参数(body=0.10-0.15, dis=0.7-1.0, near=3-5, vol=0.3-0.5)在200只测试中WR仅波动1.3pp(77.4-78.7%)。引擎的共振/序列/趋势过滤链吸收并标准化了不同质量的输入信号, 使最终交易质量趋同。这对所有SMC引擎设计有普遍意义: OB检测仅控制信号数量, 真正的质量门控在过滤链。详见 `references/v13-param-sensitivity-analysis.md`。

参数调优脚本: `/root/.hermes/scripts/v11/_v13_tune.py` — 自动patch signals_v12.py参数, 运行200只测试, 收集对比结果。可复用ID: `_v13_tune.py`。

**Dedup机制**: V474引擎的`backtest_stock_v45()`使用`used_bars = set()`跟踪已入场的entry_idx。同一股票同一bar只能产生一笔交易(第904行`if result['entry_idx'] in used_bars: continue`)。跨股票"同时同价"现象在实际data中是不同股票在同一bar索引(confirmed_at)入场, 价格不同是正常的。

**V13 60min函数在signals_v12.py中**: `detect_ob_v13_60min()`, `detect_all_signals_v13_60min()`, `detect_swings_v13_60min()`
- `detect_swings_v13_60min`: 60min专用摆动检测, right=2, ATR inversion=1.0x (Pine Waves Ultimate匹配)
- V474引擎: `/root/.hermes/scripts/v11/v474_engine.py` (V13 relaxed信号 + V467退出逻辑)
- 详细方法论: `references/v13-60min-fallback-calibration.md`

60min参数: body_pct=0.08, displacement_mult=1.0, swing +/-5, disp>=0.7x, loose volume(0.3x median)。

全量4552(V473): 376 stocks/819 trades, WR=82.8%, RR=16.75x (覆盖~60% of V11, WR/RR持平)。

### V12 已知限制

1. **CHOCH/BOS信号稀疏**: 状态机需要HH/HL交替模式,在区间震荡中不易触发。V11同样稀疏(choch=0常见)
2. **EQL极严格**: pivot-based只比较相邻摆动点,60min数据通常0-2个。正确但覆盖率低
3. **复合信号依赖于底层信号**: BPR/IFVG/BreakerBlock/OTE等信号直接复制V11实现,正确性取决于FVG/CHOCH的改进
4. **60min覆盖仅V11的~42%** (含3个代码bug): 详见 `references/v12-60min-coverage-analysis.md`。修复后V13 60min混合引擎覆盖提升到~60%。见 `references/v13-60min-mixed-engine.md`。

### 信号正确性验证方法

**发现并修复了3个bug后V12可用性显著提升**。详见 `references/v12-bug-hunt-fixes.md`。

| Bug | 位置 | 问题 | 修复 | 影响 |
|-----|------|------|------|------|
| doji终止脉冲 | line 253-256 | doji导致impulse中断, 产生大量impulse_len=1 | doji纳入impulse延长(continue而非break) | 60min多doji场景多2-3x候选 |
| impulse_len < 2过严 | line 258 | 60min数据较少连续2根阳线 | 改为 < 1 | 适配60min短脉冲特性 |
| Walrus hybrid pass | line 398 | `:=`赋值而非`==`比较, hybrid始终执行 | 删除hybrid pass, 替换为constrained forward fallback | **78%错误OB的根因** |

**Constrained Forward Fallback**: 仅在swing-backward扫描产出OB < 3时激活。比旧hybrid pass更严格:
- body >= 0.3% (过滤doji)
- 必须在摆动点8根K线内 (位置验证)
- impulse必须在i+1开始 (确保OB在脉冲前, 而非内部)

### V12 V11对比验证 (200只60min, 同入场退出逻辑)

| 指标 | V11 | V12 (修复后) | 变化 |
|------|:---:|:------------:|:----:|
| 交易数 | 1429 | 1147 | -20% |
| WR | 9.7% | **27.2%** | **+17.5pp** |
| P&L | +1371% | +1510% | +10% |

V12 swing-backward OB过滤有效淘汰噪声交易, WR达V11的3倍。**双引擎对比脚本**: `/root/.hermes/scripts/v11/backtest_compare.py` (SWITCH行13切换V11/V12)。

### V12 ⚠️ CRITICAL BUG — Walrus Operator导致Hybrid Forward始终执行 (2026-05-11)

`signals_v12.py`第398行:
```python
if swing_mode := 'hybrid':   # BUG: := 是赋值, 'hybrid'永远为True
```
应写为 `if swing_mode == 'hybrid':`。影响:
- Hybrid forward (per-candle前向扫描, 与V11的OB bug相同) 始终执行
- 在一个典型股票(600997.SH, 200根60min)上: swing_backward_v2只产出5个正确OB, hybrid_forward产出18个错误位置OB
- **78%的OB信号来自错误位置的per-candle前向扫描**
- 这是V12 200只回测WR=17.5%的根因 — 虽然swing_backward扫描正确但被hybrid淹没

### V12 附加问题: Swing-backward OB扫描产出过少

即使修复walrus operator bug, swing-backward扫描在60min数据上也有问题:
- 12个摆动高点中只有5-6个能产生有效OB
- 主要过滤点: `impulse_len < 2` — 很多摆动点回溯序列遇到连续阳线(顶部无回调), 立即进入impulse阶段但只找到1根阳线脉冲
- 60min数据比日线噪声更多, 干净的三段式(回调→脉冲→OB)结构罕见
- 建议: 放宽`impulse_len`到1或增加doji容错

参见 `references/v12-hybrid-forward-bug.md`

### 信号正确性验证方法

```python
from signals_v12 import detect_all_signals_v12
r12 = detect_all_signals_v12(ohlcv)
for ob in r12['OB_Bull'][:5]:
    print(f"OB idx={ob['idx']} → 检查前方摆动高点")
```

详见 `references/v12-signal-correction.md`。

## V12 — Corrected ICT OB Detection (2026-05-11)

V12 (`signals_v12.py`) fixes the **fundamental OB detection bug** in V11: scanning forward from every candle instead of backward from swing points.

**Key fix**: Bullish OB = bearish candle BEFORE a bullish impulse that reaches a swing HIGH. Scan backward from swing high, skip pullback bars, find impulse, then OB. See `references/v12-ict-ob-correction.md` for full details.

Results (200 stocks 60min): V12 OB coverage = 150% of V11 with correct positioning (OB 3-5 bars BEFORE swing high instead of 2-5 bars OFFSET).

## Pine Script Quality Signal Engine — signals_vPine.py (2026-05-11)

Complete rewrite of signals_v11.py with 4 Pine Script quality improvements derived from analyzing 3 reference Pine Scripts (Smart Money Concepts 2026, LuxAlgo SMC, Waves Ultimate).

### 4 Key Improvements

1. **Pine-equivalent Swing Detection** (`detect_swings_vPine`):
   - Right confirmation (left=10, right=10, like ta.pivothigh/pivotlow)
   - ATR magnitude filter (reject swings with insufficient range)
   - LuxAlgo-style volatility-aware parsing (bars with range >= 2x ATR swap high/low)

2. **OB with Displacement Filter** (`detect_ob_vPine`):
   - Hybrid mode: swing-scan primary (scan backward from swing points) + full-data scan with displacement ratio
   - Displacement must exceed 1.3x preceding bar range (from Smart Money Concepts 2026)
   - ATR-normalized strength rating (displacement/ATR ratio, volume, body size)
   - Metadata includes `displacement_ratio` for downstream entry filtering

3. **State Machine Structure Detection** (`detect_structure_vPine`):
   - Replaces rigid ICT sequence matching (Gold/Silver/Bronze) with a simple state machine
   - Tracks swing_trend (+1/-1/0), detects HH/HL transitions
   - crossover(close, last_swing_high) + trend was down → CHOCH_Bull
   - Falls back to V11 CHOCH when Pine swings are insufficient (<2 signals)

4. **Pivot-based EQH/EQL** (`detect_eql_vPine`):
   - Compares only ADJACENT swing points (not O(n^2) brute-force)
   - UAlgo-style: pivot_length=4, threshold=0.1%
   - ~93% fewer signals than V11 brute-force (which found false EQL everywhere)

### V46.1 signal accuracy + K-line sync

For BOS/CHOCH/MSS/OB accuracy fixes, use `references/v46_1-signal-accuracy-kline-sync.md`.

When the user says BOS/CHOCH/MSS/OB are still visually inaccurate, do not only change labels or tune parameters. Audit whether the pivot is a true two-sided confirmed structure point: one-sided `leg(size)` translation can anchor structure in the middle of a trend and then contaminate BOS/CHOCH, MSS, and OB. For K-line-visible structure, prefer two-sided confirmed swings (`high[k] > left(size) and high[k] > right(size)` / `low[k] < left(size) and low[k] < right(size)`) while preserving causality by confirming only at `k+size`. Keep swing BOS/CHOCH/OB separate from internal MSS. Detailed checklist: `references/v46_1-v35-signal-visual-accuracy-repair.md`.

Key requirements:
- Separate Pine/LuxAlgo structure semantics from SMC2026 OB/swing-strength semantics; do not merge them into one generic detector.
- Verify signal mechanisms before WR/RR: exact source event, zone, retest, confirmation, entry bar/price, exit bar/price.
- K-line labels are verification tools, not decoration. Show full readable labels: `BOS↑/↓`, `CHOCH↑/↓`, `MSS↑/↓`, `LIQ`, `OB`, `FVG`.
- After signal-engine changes, synchronize backtest, true watchlist/active picks, `/api/kline_full`, K-line marks, analysis, and autopsy outputs.

### Key Design Decisions

- **Same interface as V11**: `detect_all_signals_vPine(ohlcv)` returns same dict format
- **Backward compatible**: v470_engine.py just changes the import from signals_v11 to signals_vPine
- **Hybrid OB mode**: swing-scan for precision + full-data scan for coverage
- **V11 fallback**: CHOCH/BreakerBlock/IFVG/BPR kept identical to V11 for non-essential signals

### V470 Results (full 4552)

| Metric | V468 (old) | V470 (Pine-quality) | Change |
|--------|-----------|--------------------|--------|
| Stocks | 561 | 452 | -19.4% |
| Trades | 1318 | 1056 | -19.9% |
| WR | 58.0% | 57.7% | -0.5% |
| RR | 5.64x | **6.37x** | **+12.9%** |
| P&L/笔 | +2.42% | +2.52% | +4.1% |

RR improved 12.9% through better OB selection (displacement filter filters out low-quality OBs). Coverage drops 19% as trade-off.

### Files

- `/root/.hermes/scripts/v11/signals_vPine.py` — Complete signal engine (~2000 lines)
- `/root/.hermes/scripts/v11/v470_engine.py` — V470 backtest engine (uses signals_vPine)
- `/root/.hermes/smc_opt_v470/` — V470 full results (452 stocks, 1056 trades)

### Pitfalls

- **Pine swings are too sparse for 200-bar data**: Right=10 confirmation means only ~8 swings in 200 bars. Structure state machine needs V11 fallback.
- **displacement_ratio in hybrid mode**: When no swing within 25 bars, falls back to 10-bar forward range. This works but is less precise than swing-based displacement.
- **metadata spreads in to_dict()**: Signal.to_dict() uses `**self.metadata` which spreads metadata keys to the top level. Debugging must check top-level keys, not nested `s['metadata']`.
- **OB count unchanged**: Despite displacement filter, hybrid mode produces same OB count as V11. Quality improvement comes from metadata (displacement_ratio) that the entry engine uses, not from OB count reduction.
- **V11 CHOCH fallback necessary**: State machine needs >5 swing points; Pine swings (right=10) produce too few. Fallback ensures coverage.

### Reference Pine Script Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| ob_displacement_mult | 1.3 | Smart Money Concepts 2026 |
| ob_swing_length | 7 | Smart Money Concepts 2026 |
| ob_lookback | 20 | Smart Money Concepts 2026 |
| swing_length (structure) | 10 | Smart Money Concepts 2026 |
| eqhl_pivot_length | 4 | LuxAlgo SMC |
| eqhl_threshold | 0.1% | LuxAlgo SMC |
| swing_left | 10 | Pine Script pivothigh/pivotlow |
| swing_right | 10 | Pine Script pivothigh/pivotlow |

## V3.2 全量多周期分窗口回测 (2026-05-14) ⭐ 最新

数据: 4836日线(100%) / 2725真实周线(56%, Hubble补充+1600) / 4551 60min(94%)
有效序列: 2250只

### 核心结论

| 周期/趋势/模式 | WR | N | 说明 |
|---------------|-----|-----|------|
| **日线 bullish+S→D** | **94.8%** | 984 | ⭐ 最优策略, 三窗口极稳定 |
| 日线 bullish+L→D | 88.6% | 1124 | 主力模式 |
| 日线 bearish+L→D | 86.8% | 516 | 熊市唯一有效 |
| 60min S→D | 68.7% | 569 | 远弱于日线 |

- **日线 >> 60min** (94% vs 69%), 跨周期模式仅32%一致
- **做空全部无效** (WR<50%), A股T+1限制
- **窗口稳定**: 日线S→D full=94%→mid=94%→recent=93%

详见 `references/v32-cross-cycle-backtest-report.md`

### 数据下载: subprocess+curl 方法

Python urllib对东方财富(SSL error)和腾讯(302 redirect)不可靠。正确方法:

```python
import subprocess
cmd = ['curl', '-sS', '--max-time', '15', url]
resp = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
```

Hubble API支持周线(`interval=weekly`), 覆盖~1600只A股。缺失周线用日线合成(`daily_to_weekly`)。

周线数据文件: `kline_cache/*_weekly_200.json`

## 前端V2新功能 (2026-05-09)

| 功能 | 说明 |
|------|------|
| dataZoom | 鼠标滚轮缩放 + 底部滑块 + 重置按钮 |
| 信号Tooltip | 悬停显示: 类型/日期/方向/强度/置信度/价格 |
| 股票搜索 | 2+字符模糊匹配3291只股票 |
| 信号组合筛选 | All/Sweep-FVG/FVG/Sweep/CHOCH-MSS/Custom |
| 60min叠加层 | 日线+60min同图, 浅色虚线标记 |
| ECharts本地 | /tmp/echarts.min.js, 绕过CDN被墙 |

## V37 — 流动性区域检测与自适应引擎 (2026-05-09)

### 架构

V37在V36核心基础上增加了三层架构:

```
Layer 1: 流动性区域检测 (liquidity_v37.py)
  - 三级摆动点: micro(3)/meso(8)/macro(20)
  - 聚类摆动点 → BSL/SSL流动性池
  - 密度评分(越多摆动点越密集 = 流动性越大)
  
Layer 2: 猎杀追踪
  - BSL池被价格上穿 = 空头止损猎杀
  - SSL池被价格下穿 = 多头止损猎杀  
  - 猎杀后1-3根K线内反转 = 成功猎杀
  - 猎杀后未反转 = 假突破/趋势延续

Layer 3: ATR自适应序列窗口
  - 高波(ATR>3.5%): tight[3]/medium[4]/loose[6]
  - 中波(1.5-3.5%): tight[4]/medium[6]/loose[8]
  - 低波(<1.5%): tight[5]/medium[8]/loose[12]
```

### 关键发现

| 发现 | 说明 |
|------|------|
| 猎杀覆盖度提升 | V37发现8.1/stock vs V11的4/stock (2x) |
| 猎杀→FVG比率 | 仅27%的猎杀在5根K线内产生FVG |
| 流动性对WR影响 | 有猎杀WR=34.6% vs 无猎杀WR=38.3% — 几乎无差别 |
| 结论 | A股日线特性决定流动性猎杀在日线层面无效 |

### 为什么流动性猎杀在A股日线无效

1. **日线gap特性**: 99.6%交易在1根K线退出, 次日开盘决定胜负
2. **猎杀发生时间**: 流动性扫荡通常在盘中完成, 日线无法精确捕获
3. **SL太紧**: V36的0.3%SL在gap下被轻易打掉
4. **需要intraday**: 60min/15min数据才能捕获真正的ICT猎杀→反转模式

### V37文件

| 文件 | 说明 |
|------|------|
| `v11/liquidity_v37.py` | 流动性区域检测, 猎杀追踪, 自适应窗口 |
| `v11/backtest_v37_core.py` | V36核心+流动性过滤的回测引擎 |
| `v11/scan_full_market_v37.py` | 全量4800扫描脚本 |

### 信号发生时间顺序的时间范围定义

信号序列窗口根据ATR自适应:

| 波动率 | 紧窗口(tight) | 中窗口(medium) | 松窗口(loose) | 序列最大跨度 |
|--------|-------------|--------------|-------------|-----------|
| 低波(<1.5%) | 5根K线 | 8根K线 | 12根K线 | 20根K线 |
| 中波(1.5-3.5%) | 4根K线 | 6根K线 | 8根K线 | 15根K线 |
| 高波(>3.5%) | 3根K线 | 4根K线 | 6根K线 | 10根K线 |

定义:
- **紧窗口(tight)**: 同方向连续信号间的最大间隔。Sweep→CHOCH应在tight内。
- **中窗口(medium)**: 序列第一步到第二步的最大间隔。CHOCH→FVG应在medium内。
- **松窗口(loose)**: 序列第二步到第三步的最大间隔。FVG→OB应在loose内。
- **序列最大跨度**: 整个序列从第一步到最后一步不得超过此值。

## 最终结论 (V28-V37完全迭代后)

### A股日线SMC交易的核心真理

1. **紧SL+保本trailing不可替代**: 0.3%SL在V28-V37所有版本中最优
2. **1-bar退出是结构性**: 日线gap决定99.6%交易在1根K线结束
3. **信号修复有效但有限**: V11.2修复提升WR从84%→86%, RR从3.09→3.46
4. **复杂化不改善**: 多信号组合/共振/链码/POI都未能超越V36基础方案
5. **结构性TP是唯一突破**: swing_high TP, WR=96%, 78%交易使用

### 阻碍进一步改进的因素

1. **Hubble API 401**: 60min/周内/ETF数据不可用 — 无法实现真正的多周期
2. **缺少intraday数据**: 流动性猎杀在日线层面无法精确捕获
3. **A股日线固有特性**: 涨跌停板、T+1、集合竞价使日线形态与期货/Crypto完全不同

## V28 FINAL — 清洁基线 (全量4800已验证)

> 🔧 **Auto-audit maintenance**: see `references/v28-auto-audit-pipeline.md` for the recurring cron-driven scan → diagnostics → fix → verify → cache-refresh workflow.

| 指标 | V28 (200只) | V28 (全量4800) |
|------|-----------|-----------------|
| 可交易 | 131/200 (65.5%) | 3291/4800 (68.6%) |
| 交易数 | 693 | 18,054 |
| WR | 76.6% | 77.1% |
| RR | 5.94x | 7.24x |
| PF | 27 | 35 |
| WR>=80% | 70 | 1,679 |
| 平均持有 | 1.0 bars | 1.0 bars |

### V28 架构

### 架构: 3层信号时序

V34在V33链码基础上增加了POI(兴趣点)检测和价格行为上下文分类:

```
Layer 1: POI检测 — 每个FVG的lower边界自动成为POI(支撑位)
Layer 2: 价格行为上下文 — 4种场景自动识别
  - Fresh(新鲜): FVG出现后价格从未回测POI → 基础分0.50
  - POI回调: 价格曾到POI→离开→回来 → WR=87.0% ⭐
  - 趋势延续: 多周期趋势向上+价格回调到POI → WR=77.9%
  - 反转: CHOCH+FVG在结构转折点 → 待验证
Layer 3: V33链码匹配(保留)
```

### V34 200只验证结果

| 上下文 | 交易数 | WR | P&L | 建议 |
|--------|-------|----|-----|------|
| POI回调 | 193 | **87.0%** | +1.53% | 黄金场景, 无条件入场 |
| 趋势延续 | 298 | **77.9%** | +1.54% | 优秀, 强烈推荐 |
| Fresh(无回测) | 915 | 66.8% | +1.54% | 一般, 严格过滤 |

### 全版本对比

| 版本 | 核心改动 | 可交易 | WR | RR | PF | P&L |
|------|---------|--------|----|----|----|-----|
| V28 | 清洁基线(SL=0.3%+trailing) | 131/200 | 76.6% | 5.94x | 27 | +1.59% |
| V33 | 链码模式匹配 | 114/200 | 71.3% | 4.85x | 24 | +1.47% |
| V34 | POI+价格上下文 | 109/200 | 71.9% | 5.10x | 26 | +1.54% |
| V35 | 固定SL/TP(0.5-1.0%) | 171/200 | 36.1% | 2.12x | 2 | +0.50% |
| V35.1 | 延迟trailing(+2%触发) | 181/200 | 37.4% | 4.13x | 5 | +0.98% |

### 核心结论

1. **1-bar退出不可改变**: 99.6%交易在1根K线退出, 次日的gap决定胜负。这是A股日线紧SL策略的本质, 不是bug。
2. **V28紧SL+breakeven trailing最优**: 固定SL/TP方案(V35)WR暴跌到36%, 因为日线波动太大, 0.5%SL被随机噪音打掉。
3. **POI回调场景比链码更有用**: 价格回测FVG lower后再入场, WR=87% vs 新鲜FVG的66.8%。
4. **最佳入场模式**: OFC(OB→FVG→CHOCH) WR=88%, SF(Sweep→FVG) WR=78%。

## V36 — SMC结构性SL/TP (2026-05-09)

### 核心改进

替换V28的固定百分比SL为基于SMC结构的止盈止损:
- **结构SL**: FVG下边界(缺口填充=信号失效), OB下边界(跌破订单块), 摆动低点, ATR自适应保底
- **结构TP**: 前方CHOCH break_level(最可靠结构阻力), 前方摆动高点(次选)
- **结构感知trailing**: 有TP时接近目标收紧, 无TP时宽松抓趋势

### V36 200只验证结果

| 指标 | V28 (基线) | V36 (结构SL/TP) | 变化 |
|------|-----------|----------------|------|
| 可交易 | 131/200 (65.5%) | 150/200 (75%) | +14.5% |
| 交易数 | 693 | 868 | +25% |
| WR | 76.6% | **84.0%** | **+7.4%** |
| RR | 5.94x | 3.09x | -47% (SG更宽) |
| PF | 27 | 24 | -3 |
| P&L | +1.59% | **+2.08%** | **+31%** |
| WR>=80% | 70 | 104 | +49% |

### SL类型表现

| SL类型 | 占比 | WR | 说明 |
|--------|------|----|------|
| adaptive (ATR动态) | 82.6% | 84.8% | 主力, 优于固定0.3% |
| swing (摆动低点) | 14.9% | 79.8% | 比V28的74.2%提升 |
| structure_fvg (FVG下边界) | 1.4% | 75.0% | 小样本(缺口太小) |
| structure_ob (OB下边界) | 1.2% | 90.0% | 优秀但罕见 |

### TP类型表现 (最核心发现)

| TP类型 | 占比 | WR | avgP&L | 说明 |
|--------|------|----|--------|------|
| **swing_high** (摆动高点) | **78%** | **96.0%** | **+2.64%** | ⭐ 核心盈利来源 |
| choch (CHOCH break) | 3% | 89.3% | +1.27% | 好但少 |
| none (无结构TP) | 19% | 33.1% | -0.13% | 亏损来源, 应过滤 |

### 关键发现

1. **结构TP是游戏改变者**: 78%交易有`swing_high`结构TP, WR=96.0%。只要前方有清晰的结构阻力位, 交易几乎必赢。
2. **无结构TP的交易是噪声**: 19%交易WR=33.1%, 这些交易缺乏清晰目标, 应被过滤。
3. **ATR自适应SL有效**: 替代固定0.3%SL, 82.6%交易WR=84.8%。根据近期波动率动态调整。
4. **V36架构**: 基于V28引擎, 新增 `calc_structural_sl`, `calc_structural_tp`, `calc_trailing_v36`。
5. **文件**: `/root/.hermes/scripts/v11/rolling_backtest_v36.py`, 结果保存到`/root/.hermes/smc_opt_v36/backtest_v36.json`。

### 全版本对比

| 版本 | 核心改动 | WR | RR | PF | P&L | 关键结论 |
|------|---------|----|----|----|-----|---------|
| V28 | 清洁基线(SL=0.3%+trailing) | 76.6% | 5.94x | 27 | +1.59% | 不可动摇的基线 |
| V34 | POI+价格上下文 | 71.9% | 5.10x | 26 | +1.54% | POI回调WR=87%但覆盖率低 |
| **V36** | **结构性SL/TP** | **84.0%** | 3.09x | 24 | **+2.08%** | **结构TP(swing_high) WR=96%** |

详见 `references/v36-structural-sl-tp.md`。

## V28 FINAL — 清洁基线 (全量4800已验证)

> 🔧 **Auto-audit maintenance**: see `references/v28-auto-audit-pipeline.md` for the recurring cron-driven scan → diagnostics → fix → verify → cache-refresh workflow.

| 指标 | V28 (200只) | V28 (全量4800) |
|------|-----------|-----------------|
| 可交易 | 131/200 (65.5%) | 3291/4800 (68.6%) |
| 交易数 | 693 | 18,054 |
| WR | 76.6% | 77.1% |
| RR | 5.94x | 7.24x |
| PF | 27 | 35 |
| WR>=80% | 70 | 1,679 |
| 平均持有 | 1.0 bars | 1.0 bars |

### V28 架构

### V28 架构

```
信号类型: FVG Bull-only (OB仅2.4%)
入场时机: confirmed_at bar的close (FVG: idx+1)
入场价格: ohlcv[entry_bar]['c'] (当前bar收盘价)
SL: 摆动点(0.10-0.70%) 或 固定(0.3%)
退出: 追踪止盈 (0.2%→保本, 0.5%→+0.2%, 1%→+0.5%, 2%→最高-1%, 4%→最高-2%)
信号新鲜度: 无限制
```

## 已知陷阱

0. **⚠️ OB_Bull不需要序列/自适应/多TF (V11 FINAL, 2026-05-14)**:
   OB_Bull standalone WR=94.2% PnL=+2.59%。91% OB已含摆动结构验证。
   序列(LIQ→ZONE等)仅匹配5-23% OB且不提升WR。动态SL降至75.3%, 60min共振降至75.9%。
   最优: OB_Bull→T+1开盘买→SL=OB.lower×0.995→TP=+3%→5bar超时。无需组合。
   详见 `references/ob-only-942wr-discovery.md`。

1. **⚠️ ENTRY_PRICE前视偏差 (CRITICAL)**: V23-V25使用`entry_price = dec.get('entry_price')`(信号bar价而非当前bar价), 所有结果被系统性高估。V25 WR=90.8%/RR=74.4x/PF=987完全无效。修复: `entry_price = ohlcv[i]['c']`。

2. **V35固定SL方案WR<40%**: 日线波动使得0.5%SL产生63.8%亏损率。固定SL不适合A股日线SMC交易。

3. **V34 POI回调场景仅35%覆盖率**: 只有193/1406笔交易进入POI回调场景, 大多数交易仍是Fresh(66.8%)。

4. **Python HTML模板bug**: `"A" + B if C else "D" + "E"`中`+`比`if-else`优先级高, 导致模板截断。应使用`{placeholder}`替换模式。

5. **ECharts CDN被墙**: jsdelivr.net在服务器上无法访问。解决: 下载到本地`/tmp/echarts.min.js`, 通过`/echarts.min.js`路由serve。

6. **⚠️ JavaScript函数未调用 (V2前端)**: `function buildSeries() { ... }` 包裹了整个chart渲染代码但从未被调用。脚本加载后chart.setOption()从未执行 → canvas=0。修复: 移除函数包装, 让代码直接在全局作用域执行。

7. **Python `.pyc` 缓存导致旧代码运行**: 修改PY文件后重启服务器, 若`__pycache__`未清除, 旧.pyc代码继续运行。修复: `find /root/.hermes/scripts/__pycache__ -name '*smc_trade_viewer*' -delete` 然后杀进程重启。

8. **ECharts 5 markArea格式兼容 (CRITICAL)**: ECharts 5的markArea数据必须使用`[[coord1, coord2], ...]`数组对格式, 不支持扁平格式`{xAxis, yAxis, xAxis1, yAxis1}`。修复:
   ```python
   # 错误: ECharts 5不渲染
   mark_areas.append({'xAxis': d, 'yAxis': lo, 'xAxis1': d, 'yAxis1': hi, ...})
   # 正确:
   mark_areas.append({'data': [{'xAxis': d, 'yAxis': lo}, {'xAxis': d, 'yAxis': hi}]})
   ```
   筛选用family/signal等元数据保持在data外层的对象上。

9. **markLine水平线含xAxis字段**: Sweep/EQL等水平信号使用`markLine`渲染时, 同时设置`yAxis`(价格)和`xAxis`(日期)会让ECharts渲染为单点而非横跨全图的水平线。修复: 只保留`yAxis`(水平线)或只保留`xAxis`(垂直线), 不同时设置两者。

10. **⚠️ Patch时意外删除关键语句 (V2前端)**: `numbered_signals.append(sig)` 在patch过程中被意外删除, 导致205个信号被检测到但全部不在渲染列表中。症状: "Signals: 205 total"但canvas为0信号。教训: patch diff只显示添加行, 但old_string中的所有其他代码会被删除。修改循环体时需确认append等关键语句仍在。

11. **所有信号使用局部线段渲染 (V2前端)**: 用户明确要求"不要使用竖线，不要满屏"。所有信号(包括CHOCH/MSS等之前是垂直线的)现在使用`_pair`格式渲染为从信号bar向右延伸的局部水平线段(约20根K线)。矩形(FVG/IFVG/OB等)从信号bar向右延伸约10根K线。详见`references/v2-frontend-debugging.md`。

12. **⚠️ Bear PnL双次取反 (V38回测)**: 做空交易trailing函数中 `return j, tp_price, True` 返回硬编码 `True`(won), 但应该检查 `tp_price < entry_price`。症状: 亏损交易被判为盈利, WR被系统性高估。修复: `return j, tp_price, tp_price < entry_price`。

13. **⚠️ 结构树TP方向 (V38回测)**: `StructureTree.get_tp_level()` 只返回摆动高点(适用于做多), 做空时需要摆动低点。修复: 添加 `direction='bull'|'bear'` 参数, bear时改找摆动低点。

14. **Python输出缓冲导致全量扫描跟踪丢失**: 长时间运行的Python回测脚本, stdout被缓冲, `tail -f` 看不到部分进度输出。修复: 使用 `python3 -u script.py` 或 `PYTHONUNBUFFERED=1 python3 script.py`。

15. **bash TERM环境变量导致后台进程输出混乱**: `bash: 无法设定终端进程组 (-1): 对设备不适当的 ioctl 操作` — 后台进程的shell没有关联终端。不影响脚本执行但输出可能乱序。修复: 在cron或background任务中, 输出重定向到文件 `> log.txt 2>&1`。

16. **⚠️ Python 3.13: `Path.read_bytes()` 返回bytes, 不可用 `json.load()`**: `json.load()` 期望文件对象, 而非bytes。修复: `json.loads(Path(path).read_bytes())`。

17. **⚠️ PYTHONUNBUFFERED=1 + 文件重定向仍可能缓冲**: 即使设置 `PYTHONUNBUFFERED=1`, shell的 `>` 文件重定向可能在用户空间缓冲。长时间运行的扫描脚本可能出现 `tail -f` 看不到输出。修复: 脚本内的 `print()` 加上 `flush=True`。

18. **⚠️ Bear TP检测方向无关乘数 (V38.0-V38.3 CRITICAL)**: `extreme <= tp_price * 0.98` 在Bear方向要求价格额外过冲2%才能触发TP退出。对于micro swing(常见0.5%距离), 实际需要从入场偏移2.5%。fix: `extreme <= tp_price * 1.02`。症状: Bear TP命中率6.3% vs Bull 41.3%。修复后升至56.7%。详见 `references/v38-4-trailing-optimization.md`。

19. **⚠️ f-string内嵌ECharts formatter字符串冲突**: ECharts JavaScript formatter如`'{b}: {c}'`在Python f-string中会被解析为f-string表达式, 导致NameError: name 'b' is not defined。修复: 在f-string中使用`'{{b}}: {{c}}'`(双花括号). 更稳妥: 将动态JS数据预构建为Python变量再`json.dumps()`, 避免f-string嵌套复杂表达式。

20. **⚠️ Python f-string中for循环不支持**: f-string表达式不支持`for`语句。修复: 预构建HTML内容为列表后用`''.join()`拼接, 再插入到f-string中。

21. **⚠️ 多HTTP服务器端口浪费**: 每个前端页面开独立进程和端口占用大量资源, 开发中不易管理。修复: 单个HTTPHandler + URL路径路由(/v1,/v2,/v3,/v4) + 导航栏切换, 详见`smc_unified.py`。

22. **⚠️ API响应缺失exit_date字段导致表格显示错误 (V12前端, 2026-05-15)**: API `/api/kline_full` 在构建trade_list时缺少`exit_date`字段，导致前端表格的"卖出日"列显示为`entry_date + hold_bars`而非实际卖出日期。修复: 在trade_list的`dict.append`中添加`'exit_date': t.get('exit_date', '')`。

23. **⚠️ 前端renderTradesTable出口日期回退逻辑错误**: JS代码`.exit_reason?((entry_date||'')+' +'+hold_bars+'b'):(entry_date||'')`始终显示entry_date而非exit_date。修复: `(t.exit_date||(t.entry_date||''))`。

24. **⚠️ detect_ob_v14死代码 (V44引擎)**: V44的v44_engine.py定义了`detect_ob_v14`(277-548行, 含趋势上下文+质量评分+突破验证), 但`backtest_stock_v44`调用的是`detect_all_signals_v11` → `signals_v11.py`中的`detect_ob_v11`。V14 OB从未参与任何交易决策。教训: 新组件定义后必须立即集成到主流程或删除。定义但不集成的代码消耗后续开发者的认知资源, 且不会被测试覆盖。

23. **⚠️ 信号数量不等同于交易质量**: V13 relaxed实验(2026-05-12)证明了这一点。OB/stock从28升至51(+82%), 但WR从82.7%降至82.1%。多出来的23个OB/stock是噪声。User指令明确: 信号正确性是唯一目标, 不要优化指标。当发现放松参数提升覆盖但降低WR时, 应回归到更严格的参数而非继续放宽。

24. **⚠️ 跨股票"同时同价"误解**: `v45_full.json`的`confirmed_at`是bar索引(0-199), 非时间戳。多笔交易"同时"指不同股票在第N根bar入场, 价格不同是正常。需区分: (a)跨股票聚合(正常) vs (b)单股票同bar重复(异常, `used_bars` dedup已防)。分析时勿将跨股票聚合误认为单股票bug。

25. **⚠️ quick_swing导致OB出现在趋势中途 (V14 CRITICAL BUG, 2026-05-12)**: `_quick_swing_highs(lookback=8, 无右确认)`使每个8-bar局部最高都成为摆动点。用户的观察完全正确: "OB有发生在趋势中，根本和高低点没什么关系"。根因: quick_swing = pivothigh(right=0) = 任何局部顶点。Pine标准: pivothigh(right>=2) = 确认后才是结构摆动点。V15修复: 统一使用confirmed swings (left=5,right=2)。教训: 信号检测中, 摆动点的确认延迟(right bars)不是可选优化, 而是正确性的必要条件。

26. **⚠️ CHOCH/BOS用max/min追踪极值而非最新摆动 (V15 CRITICAL BUG, 2026-05-12)**: `detect_structure_v15` line 533: `if sw['price'] > last_swing_high: last_swing_high = sw['price']` → 使last_swing_high = 全图最高点, last_swing_low = 全图最低点。突破条件`bar['c'] > last_swing_high`需要股价突破全图ATH → 300bar日线几乎不可能。Pine正确做法: `last_swing_high := swing_high_ms` (直接赋值最新值, 不取max)。症状: 600519.SH 300bar仅1个CHOCH + 2个BOS。修复后: 5 CHOCH + 4 BOS。教训: Pine中的变量赋值(= overwrite)与Python中的max更新(取最大值)语义不同。逐行对比Pine时必须精确到赋值运算符的语义差异。

28. **⚠️ Pine历史偏移vs摆动点参考系混淆 (V17 CRITICAL BUG, 2026-05-12)**: Pine `close[i]` 是相对`bar_index`(当前bar)的偏移。摆动点在`bar_index-7`。`close[8]` = bar_index-8 = 摆动点-1。V17原始代码用`sl_bar - 8`扫描(相对摆动点-8到-20)，偏差7个bar。修复: `start_back=1, end_back=ob_lookback`。详见 `references/v17-ob-scan-bug.md`。

29. **⚠️ A股参数适配 (V17, 2026-05-12)**: Pine默认(ob_swing=7,disp=1.5,min_str=3.0)设计用于数千bar高波动市场。A股300bar日线需适配: ob_swing=5, disp=1.0, min_str=2.0, ob_lookback=15, min_break_pct=0.3%。详见 `references/v17-ashare-params.md`。

30. **⚠️ OB displacement方向反转 (V17 CRITICAL BUG, 2026-05-12)**: Pine `disp = swing_low - hist_low` 检测的是capitulation模式(OB低于swing)。标准SMC要求OB高于swing(Bull)或低于swing(Bear)。修复: `disp = bar['l'] - sl_price` (Bull), `disp = sh_price - bar['h']` (Bear)。症状: 修复前半数股票OB=0，修复后CMB 0→24, 茅台1→21。详见 `references/v17-ob-displacement-fix.md`。

31. **⚠️ 小摆动触发无效CHOCH/BOS (V17, 2026-05-12)**: (5,5)摆动在300bar上产25个点含趋势中反弹。CHOCH/BOS应使用(10,10)摆动仅保留主要结构。SWEEP/MSS保留(5,5)/(3,3)检测所有层级流动性。详见 `references/v17-structural-swings.md`。

33. **⚠️ pivothigh/pivotlow 产生假结构点 (V17, 2026-05-12)**: ta.pivothigh(5,5) 在 300 bar 上产生 ~25 个点，其中 ~50% 是趋势中的反弹而非真正的 HH/HL/LL/LH。共识摆动(≥4/6 lookback)过度过滤至 13 个。**zigzag 反转摆动(2%价格反转)** 是最优解: 29 个点都是真实反转。详见 `references/v17-zigzag-methodology.md`。

34. **⚠️ displacement 硬过滤跳过正确 OB 蜡烛 (V17, 2026-05-12)**: A 股日线 swing 前的蜡烛 displacement 通常很小(0.3-0.5%)。Pine 的 displacement>1.5 硬过滤会跳过正确的最靠近 swing 的蜡烛，取远端的蜡烛(偏差 3 bar)。**first-match 逻辑**: 取 swing 前第一个反向蜡烛，displacement 仅评分不过滤。详见 `references/v17-ob-firstmatch-lesson.md`。

35. **⚠️ int日期减法跨月bug (V4监控, 2026-05-14)**: `int("20260514") - int("20260415") = 99`, 并非29天。跨月时int表示的日期差完全错误。症状: 3天过滤器返回528个信号横跨10个月。修复: `datetime.strptime(date, '%Y%m%d')` + `timedelta(days=N)`。详见 `references/live-monitor-v3-ld-pipeline.md`。

36. **⚠️ 监控信号日期范围必须紧 (V4监控, 2026-05-14)**: 30天窗口首次运行→528个信号全部已平。实时监控只能扫描最近2-3天信号, 历史信号用于回测不用于监控。

37. **⚠️ 持仓刷新需merge逻辑 (V4监控, 2026-05-14)**: 旧monitor首次从picks创建持仓后永不更新。修复: 每次运行merge新picks(以symbol|date|chain去重), 保留已有持仓的盈亏记录。详见 `references/live-monitor-v3-ld-pipeline.md`。

38. **⚠️ TP/SL 仅检查最后bar遗漏中间穿越 (V3监控 CRITICAL, 2026-05-14)**: `get_current_price()` 从腾讯API只取最后一根日K的 high/low 检查TP/SL。如果TP在中间bar被触发（如 bar=299 h=48.98 ≥ TP=48.07），但监控首次运行时 bar=300 已覆盖，该触发被永久遗漏。症状: 002289_SZ 本应 TP+3%，显示为"持仓中 +0.3%"。修复: 遍历 `kline_cache` 中的完整日线数据，从 entry_bar+1 到最后一根 bar，逐根检查 high≥TP 和 low≤SL。先检查 TP（有利），后检查 SL。详见 `references/live-monitor-v3-ld-pipeline.md`。

39. **⚠️ 组合信号结构问题 (2026-05-14)**: LIQ/STRUCT bar 经常同时含 ZONE 信号(6/12样本); zone_low 距 entry 5-17% 导致 SL cap 失去结构意义; gap=1 序列可能是噪声(3/12)。详见 `references/combo-signal-structural-audit.md`。

39. **⚠️ 组合信号结构问题 (2026-05-14)**: OB_Bull天然与LIQ同bar导致序列永远匹配不到; FVG zone_low距entry 5-17%无法做结构SL; FVG组合vs孤立FVG +10pp WR提升(74.5% vs 64.5%), 组合逻辑成立; 分层系统L1(OB 89.5%) L2(FVG gap≤10 ~78%) L3(FVG gap>10 ~72%)。详见 `references/combo-signal-structural-audit.md`。

40. **⚠️ find_tps/find_sls requires swings_dict (2026-05-14)**: `v19_backtest_engine.py`中`find_tps/find_sls`访问`swings_dict.get('highs', [])`。传`None`会导致`AttributeError`。始终传`detect_all_signals_v20()`的swings_dict。此bug导致timerange回测初版崩溃。

41. **⚠️ zigzag SWEEP idx

## ⚠️ 入场方式关键教训 (2026-05-14)

**ENTRY_AT_ZONE不适用于序列系统。** V17在单信号下证明ZONE入场 WR=94.2% vs CLOSE=42.8%，但V5.0全量回测(18056笔)显示：使用序列过滤后，CLOSE入场 WR=95% 反超 ZONE入场 WR=78.3%。

根因: 序列(L→D/S→D)已自带信号质量过滤，强信号直接走不回头，回调到zone=弱信号。**序列系统用CLOSE入场，zone仅用于SL放置。**

## ⚠️ 动态SL + 多周期共振教训 (2026-05-14)

V9.0全量验证: 紧SL(zone_low*0.995)最优WR=80.3%。动态SL(ATR buffer)→75.3%，60min共振→75.9%。
**自适应价值在模式选择，不在SL调整。** 序列系统不需要动态SL或多周期硬过滤。

## V21 前端 — 信号链+交易明细 (2026-05-14 当前)

路由: `:8890/v21`, 文件: `smc_unified.py` (~560行)
数据: `detailed_trades_v60.json` (18586笔, 4205只)

关键功能:
- 全量4836只dropdown
- 信号三族开关: zone/liquidity/structure checkbox
- **信号链渲染**: 每笔交易前显示A(Signal)→B(Signal)→BUY, 虚线连接, 圆角矩形标记
- K线上: BUY pin(入场), SELL diamond(出场+退出原因), SL红线(20bar段), TP绿线(20bar段)
- **逐笔交易明细表**: #/入场日/入场价/信号/模式/SL/TP/出场日/出场价/退出原因/P&L/持bar

退出原因: tp_hit(52%, WR=100%), sl_hit(37%, WR=0%), time_stop(11%, WR=95.7%)

## 前端查看器 (统一服务器 port 8890) — 全量4836只

| URL | 功能 | 说明 |
|-----|------|------|
| / | 主页 | 4个模块入口 + 全局V38.4指标摘要 |
| /v20?s=600519.SH | **V20 当前版** | K线+13种SMC信号+结构标注+交易明细, dropdown全量4836只 |
| /v1?s=000001.SZ | K线+出入点 | 基于V28数据(3291只), 入场/出场标记, SL线 |
| /v2?s=000001.SZ | 13信号K线查看器 | V11信号实时检测, 数字编号+筛选, 60min叠加, 股票搜索 |
| /v17?s=000001.SZ | **V17 Pine-Exact** | 当前信号引擎, BSL/SSL标注, 强度评分 |
| /v18 | **V18 Zone-Entry Dashboard** | V17回测仪表板, WR/SL来源/入场质量 |
| /v3 | 统计仪表板 | WR分布直方图, 入口/方向饼图, Wyckoff/SL柱状图, WR=100%股票表 |
| /v4 | 高级分析仪表板 | Sankey交易流图, 分质量段累积P&L曲线, Exit Method堆叠柱状图 |
| /v5 | V45 Dashboard | Bull-only全量4800: WR=96.2%, RR=8.94x, PF=383. WR分布/SL/TP/ECharts图 |

运行: `python3 /root/.hermes/scripts/smc_unified.py` (单进程, ~400行)
数据源: kline_cache全量4836只 / V19回测数据覆盖
ECharts: /tmp/echarts.min.js

**关键**: dropdown直接从`kline_cache/*_daily_300.json`读取全部4836只股票, 不再依赖V19回测文件。无回测数据的股票仍可查看K线+信号。

V2新增13种信号: FVG, IFVG, OB, BPR, Sweep(BSL/SSL), CHOCH(BOS), MSS, OTE(斐波那契), EQL, PO3三阶段, LiquidityVoid, RejectionBlock, BreakerBlock。

每个信号带数字编号(1,2,3...)和类型缩写。入场组合显示如"68MSS 69FVG 70IFVG 71BPR"。

渲染方式: 所有信号局部化(用户要求"不要竖线不要满屏"):
- 矩形信号(FVG/IFVG/OB/BPR/OTE/PO3/RB/BRK): 从信号bar向右~10根K线, 竖向范围=信号upper-lower
- 线信号(Sweep/CHOCH/MSS/EQL/LV): 使用`_pair`格式从信号bar向右~20根K线, 水平虚线/实线@price

## V33 — 信号链码模式匹配

详见 `references/signal-timing-sequencer.md` 完整设计文档。

最佳模式:
| 模式 | 代码 | 交易 | WR | P&L |
|------|------|------|----|-----|
| OB→FVG→CHOCH | OFC | 8 | **88%** | +3.25% |
| Sweep→FVG | SF | 18 | **78%** | +1.87% |
| FVG→FVG | FF | 384 | 73% | +1.19% |
| 孤立FVG | — | 738 | 73% | +1.53% |
| OB→OB | OO | 64 | 70% | +1.83% |
| OB→FVG | OF | 99 | 69% | +1.31% |

## V30-V31 迭代结论

| 版本 | 改动 | 可交易 | WR | RR | PF | 结论 |
|------|------|--------|----|----|----|------|
| V28 | confirmed_at入场(基线) | 131 | 76.6% | 5.94x | 27 | 当前最佳 |
| V30 | 每股SL优化(4值)+摆动扩大+新鲜度 | 128 | 67.3% | 6.07x | 24 | SL=0.3%最优(99%), 新鲜度过严 |
| V31 | FVG评分+宽trailing(+1.0%保本) | 127 | 62.8% | 6.64x | 15 | 宽trailing减少交易+降低WR |

## V26 — entry_price修复 (V23-V25全部无效)

V23-V25因`entry_price`前视偏差(V25 WR=90.8%/RR=74.4x/PF=987)无效:
- 修复: `entry_price = ohlcv[i]['c']`
- V26(bar-循环): 35/200可交易, WR=66.7%, RR=3.31x — 125-bar信号延迟
- V27(信号驱动+signal_idx): 122/200可交易, WR=87.6%, RR=8.37x — 1-bar预确认偏差
- V28(信号驱动+confirmed_at): 131/200可交易, WR=76.6%, RR=5.94x — 清洁基线

## V11.3-V23 完整迭代史

详见references目录中各参考文件。

## 参考文件

- `references/5-parallel-signal-engines.md` — **5套并行信号引擎架构分析 (2026-05-25)**: V11/v22/V44/Pine-like/LuxAlgo V34 互不兼容，导致回测/前端/选股三方信号不一致
- `references/v12-60min-coverage-analysis.md` — V12 swing-backward OB在60min数据上的覆盖限制, V472引擎适配方法
- `scripts/backtest_compare.py` — V11/V12双引擎一键切换对比测试脚本(200只60min)
- `scripts/compare_signals_v12_vpine.py` — V12 vs V-Pine信号数量对比诊断脚本
- `references/v38-multi-adaptive-system.md` — V38多自适应共振系统(结构树/Wyckoff/做空/PnL陷阱)
- `references/v11-signal-fixes.md` — V11.2 9项信号修复详情
- `references/60min-data-integration.md` — 60分钟数据源测试+集成
- `references/multitf-backtest-results.md` — Multi-TF多周期回测结果
- `references/v37-liquidity-detection.md` — V37流动性区域检测详细会话记录
- `references/v2-frontend-debugging.md` — V2前端调试日志(2026-05-09修复)
- `references/v2-frontend-features.md` — V2前端新功能(zoom/tooltip/search/combo/60min)
- `references/v36-structural-sl-tp.md`
- `references/v36-structural-sl-tp.md` — V36结构性SL/TP详细设计+结果
- `references/structure-sl-tp-and-new-signals.md` — 结构SL/TP+14种信号说明
- `references/backtest-data-validation.md` — 回测数据验证方法论
- `references/backtest-v3-summary.md` — V11.2回测详细分析
- `references/architecture-v11.md` — 系统架构图
- `references/v17-multi-tf-design.md` — V17多周期框架
- `references/v25-trailing-stop.md` — V25追踪止盈策略
- `references/signal-sequence-patterns.md` — 信号序列模式分析
- `references/optimal-params.md` — 最优参数参考
- `references/v23-final-strategy.md` — V23最终策略配置
- `references/board-analysis.md` — 按板块分析(V21全量4800)
- `references/price-validation.md` — A股价格验证分层标准与算法 (absorbed from `price-validation-smc`)
- `references/v44-engine-details.md` — V44引擎架构、回踩入场、质量分级trailing、关键Bug (absorbed from `smc-engine-v44`)
- `references/frontend-architecture.md` — ECharts渲染陷阱、信号绘制架构、服务器健康检查、端口清理 (absorbed from `smc-unified-frontend`)
- `references/v2-frontend-debugging.md` — V2前端调试日志(2026-05-09修复)

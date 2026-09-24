# SMC 自适应迭代总结收档 (R89 → R108, goal round 1→21)

日期： 2026-09-24 | 目标： "BOS/CHoCH, BSL/SSL, MSS, LL/LH/HL/HH 自动化适应， 跨股票/周期/时间段深入迭代"

## 一、 判定到可回弛的数据 (点击全)

### 引擎层 （新自适应， norm 模式）
| 操組 | 文件 | 联质义 |
|---|---|---|
| 概基础 | `research/core/structure.py` | `pick_pivot_by_density` + `structure_events(mode='auto')` (ATR 穿透缘 0.15×) |
| 链包 | `research/core/chain.py` | `build_chain(mode='auto')` + `_hh_ll_sequence` （显式 HH/HL/LH/LL) |
| enrich | `research/gen_smc_full_v2_r94.py` | detector 全换成 norm, 出 `combo_v22_smc_full_v2.csv` (1524 腿） |
| 生链 | `research/r90_chain_regen.py` | `combo_v22_chain_v2_norm.csv` (1858 腿链） |
| 结构并联合表 | `research/r101_hhll_chain.py` | `combo_v22_chain_v2_hhll.csv` （链 + structure_state) |

### 数据证据
| 点 | 结果 |
|---|---|
| BSL/SSL sweep 池 | 244→126 bear (norm) — 机称假阳流起响 |
| MSS_id 翻转率 | 31.4% |
| 分股 pivot 分布 | 60.5%选5 / 34.1%选4 / 各 0.2% 端场 3/8 — 没坍缩 |
| 密度意识后 | 9.2~13.6 swings/100bar， 100% 株选 [8,14] 带 |
| 显式结构桶 | bull(HH+HL)×BOS↑×retok 最伤 PF 1.77 (64腿） |
| | bear(LH+LL)×CHoCH↑×noret PF 1.73 (38 腿） |

### 组合手术表 （狠打终版） — R94 powergrid + R101 s22/s23
| 项 | 狠打权重 |
|---|---|
| s1 (CHoCH) | 0.4 |
| s7 (trend=up) | 0.5 |
| s15 BOS↓+retfail | 0.5 |
| s16 up+no_retrace | 0.6 |
| s17 down+ret_ok | 1.1 |
| s18/s19 (CHoCH↑ × noret / retfail) | 0.35 |
| s20 CHoCH↓ × retfail | 0.35 |
| s21 BOS↑ × retfail | 0.4 |
| s22 bull-structure × BOS↑ × retok | 0.15 |
| s23 bear-structure × CHoCH↑ × noret | 0.15 |
| s4/s5/s6/s13/s14 | 同 v1 |

### 交付的判定对照单
| 变量 | fit (≤2025) / n=1467 | OOS (2026) / n=391 | 判定 |
|---|---|---|---|
| 等权 | PF 3.09 | PF 4.38 | — |
| v24 v1 链 （生产） | PF 6.30 | PF 4.56 | 生产候选工等 |
| **v2 全链狠打 (+s22/23)** | **PF 7.02** | **PF 4.90** | ✅ 场供比 v1 +0.34 OOS |

## 二、 生产侍序
- paper_ledger 148 订单发双影子 (v23 / v23_v2), 备份 bak_r96/r105
- paper_sim._v23v2_of 与 v23 另行挂载， 开已一起深 踏在地堆中
- config.py `V23_V2_AS_PRODUCER` (默认 False, 剈产时才会切）
- **复盘日 2026-10-23: 只需重跑 `r99_review_judgment.py` 或 `r106_daily_shadow_reconcile.py`**

## 三、 前同全同护
- `/kline`: 腿表 + tooltip 含 v2 全链影子 + structure_state
- `/audit`: 生产影子池 + 双链复盘卡 + 双链分歧警报 (24 个 v1高v2狠）
- `/kline` 的 chart: leg marker + sweep + FVG + BSL/SSL 链标全存档到 (R88 + R96)

## 四、 剩余 (技当 0)
1. **Jev API key 轮换** — 聊天串里待激 (由用户手动走， AI 不可踩安全接口） 
2. **复盘日 2026-10-23 计划召升的 TZA** — 等判定结果， 一键 `r106_daily_shadow_reconcile.py` 出汇报疑大色牵瑞丰口有例子感觉
3. **诱让 V23_V2_AS_PRODUCER=1 之真点昌** — 由用户按 /audit 卡片判定 （研究不是市集）

## 五、 代码提交史
- `R89 → R95 → R96+R97 → R98 → R99 → R100 → R101 → R102 → R103 → R104 → R105 → R106 → R107 → R108`
- 本版: `c15d232` (end)

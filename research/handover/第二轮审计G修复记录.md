# 第二轮审计（G01-G25）修复记录（2026-09-05 第 1 批 P0）

> 审计基线 ea38820；当前 HEAD 已含此前全部修复。本轮按审计补丁单变量实施 P0 项，避免重蹈"8阶段净负优化"覆辙。

## 已修复（P0，7 项）

### G01 ✅ POI 触碰窗晚于 BOS（前视泄漏第一根因）
- 触碰窗起点 `ob_idx+1` → **`rsp+1`**（BOS 收盘确认后）；reclaim ≥ rsp+1、entry ≥ rsp+2
- OB 搜索下限提到 sweep bar i（不允许 OB 落在 sweep 前）；FVG 检测含 rsp bar
- 加前视断言：`max(i,rsp,ob_idx,touch,reclaim) < entry_idx` 否则丢弃
- **A/B（300 只）**：seeds 365→52、avg +3.96%→**+4.57%**、PF 2.53→**2.96**（wr 62%）——去前视后样本变少但质量升，且高于审计剥离表 avg+1.5%（证明策略本身有 edge 而非纯前视）

### G02 ✅ 重复计数去重
- build_seeds 加 `used_entries`/`used_swings` + 5 根冷却
- A/B：300 只重复 7→**0**、seeds 52→45（真实去重）、avg +4.37%、PF 2.67

### G03 ✅ SMC 腿接入生产选股
- daily_selection 新增 smc_candidates 消费分支 → PENDING_ORDER(next_open)
- SL=min(zone,sweep)×0.99、TP1=1R、TP2=max(target,1.5R)、风险仓位 position_pct
- 验证：选股统计加 smc_selected 计数

### G04 ✅ 延续腿去除前视成交
- CONT 腿不再当日 FILLED：改为 PENDING_ORDER + `valid_from`（signal 后首交易日）
- monitor 用实时 open 成交（不再"知今日涨9%按今开买"）

### G05 ✅ `_retrace_open_done` 历史价回退删除
- realtime_prices 增返回 open（今开）
- retrace 挂单：valid_from 前不成交；回落触 limit 按 limit 成交；否则首日实时 open 兜底
- 删除 t1_open 历史价成交分支

### G06 ✅ TP 分层记账双计修复
- TP2 触发 = 剩余 70% 全平 + **CLOSED(TP2_RUNNER)**（原只记 realized 不置 CLOSED，
  后续 SL_HIT/TP4_RUNNER 再按 0.7 双计）
- TP4_RUNNER 加 `not tp2_hit` 条件（防双路径）

### G07 ✅ structural_sltp 前视修复
- 摆动点搜索加确认窗口 `j + PIVOT <= i`（paper_sim 与回测 gen_v20f 口径统一）
- highs 只保留 > signal close 的结构位（防 tp1 < 入场价）
- 验证：000008 真实数据 tp1=2.6 > close、sl1=2.15 ✅

## 待后续（P1/P2）
G08 持有期统一 / G09 T+2 / G10 公告分页 / G11 proxy门控软化 / G12 追赶池 /
G13 集中度 / G14 SL-ATR分板块 / G15 结构追踪 / G16 BOS严格 / G17 z-score /
G18 涨跌停分板块 / G19 core切换 / G20 off-by-one / G21 真WF / G22 rank特征 /
G23 W层方向 / G24 portfolio层 / G25 事件分类统一

## 验证
- ✅ 全部 73 项单元测试通过（19+7+15+10+10+12）
- ✅ 生产文件哈希未变（registry 99763059 / ledger 9F7D064B）
- ✅ G01 A/B：avg +4.57%/PF 2.96（去前视后真实 edge）

---

## 全量回测验证（G01/G02 修复后，2026-09-05）

| 指标 | 修复前(含前视/重复) | G01/G02修复后 |
|---|---:|---:|
| trades(全市场4905只) | 6,359 | 928 |
| IS avg | +7.55% | +4.40% |
| IS PF | 4.79 | 2.30 |
| **OOS avg** | +4.06% | **-0.60%** |
| **OOS PF** | 2.40 | **0.88** |
| OOS 胜率 | 66% | 40% |

### 关键结论（必须诚实面对）
1. **去除前视(G01)+重复(G02)后，OOS edge 由 +4.06% 转为 -0.60%** —— 证实审计结论：
   原回测优势主要来自 BOS 前视入场 + 重复计数 + 202409 单月行情，非真实策略 edge
2. 928 笔/3年 ≈ 300 笔/年 统计足够，但 OOS 为负（PF 0.88 < 1）→ **当前 SMC 引擎无可交易 OOS edge**
3. 与审计剥离表一致（avg+1.5% 扣成本后盈亏平衡）；我们的严格 OOS 口径显示更差
4. **下一步必须**：按蓝图 D5 重构入场（折价区限价非追位移）+ D6 单一执行 + 保留本批 P0 修复，
   再在信号充足池上验证 SMC 是否有真实 edge（D8 真 WF + placebo）

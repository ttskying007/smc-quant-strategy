# -*- coding: utf-8 -*-
"""v4_audit_map.py —— 审计蓝图 §16.4 十二步 vs 本 session 实际完成度对账表(审计目标的核心交付物)
每一步: 审计要求的验收标准 → 本机证据(章节/文件/判定号) → 状态(已完成/进行中/未开始)
这就是审计文档自己说的'必须使用逐笔交易数据进一步验证的问题'的答卷。"""
import io, json, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

STEPS = [
    ("1. 建立唯一生产合同(release manifest)",
     "前端版本=扫描器版本=纸面交易版本=账本版本",
     "production_registry.json V2 = 唯一 manifest(MD5 9976...C525 每次提交核验); "
     "smc_unified ACTIVE_VERSION 由 registry 唯一决定(§51 核查); 前端 COMBO 分支读 combo_dashboard+paper_ledger 与生产账本同源",
     "已完成"),
    ("2. 清理版本体系(Git tag/删历史候选)",
     "版本绑定参数与数据快照",
     "本 session 全部工作 Git 提交+推送(每步 registry MD5 同步核验); 但 72 个 smc_opt_* 历史目录仍在 hermes/(Linux 前端区, 生产链不读) —— 死代码清理记录为低优先(§51 采纳项3)",
     "进行中(Git 治理✓ / 历史目录清理待做)"),
    ("3. 未来函数专项审计",
     "Swing/BOS/FVG/OB 确认时点/高周期对齐/退出无未来数据",
     "no_lookahead 3 用例+causality 红线库(535 基线内); V88/V86/V85 前视偏差 2026-08-17 否决(registry lineages); 公告 D→valid_from 无前视窗(§46 P3); F7 数据对齐伪影揭露(§53)",
     "已完成"),
    ("4. 重构 SMC 事件状态机",
     "形成→确认→可交易→触碰→回补→失效→过期",
     "V3-A 语义锁: seeds 状态机(detected_at/confirmed_at/tradable_at 全透传)+valid_from/EXPIRED(PENDING→FILLED/EXPIRED→OPEN→CLOSED, §37); G05/G09 修复链",
     "已完成"),
    ("5. 拆分事件腿和延续腿",
     "独立统计收益/相关性",
     "双台账分离: v0 paper_ledger(EVENT)/PAPER setup 台账(结构腿)+SHADOW; 跨腿重叠审计交集=∅(§47); EVENT n=1640 avg+3.72 vs CONT n=113 独立; §44 费用口径四系统同源",
     "已完成"),
    ("6. 放宽 V517 量能门槛(分层评分)",
     "Top20/Top50/观察 三层",
     "V517/V519/V526 本机生产链零引用(§51 过期快照); 现行事件腿用 v_ratio(F17 规模解析)+rank_score(§40 正交验证 ρ=0.171)分层 —— 结构不同但分层语义已具备",
     "已完成(不同实现路径)"),
    ("7. 修复选股漏斗(逐层拒绝原因)",
     "每日输出每层过滤数量+拒绝原因",
     "structure_funnel_daily(13950bar 全漏斗 L1-L7+drop_reasons 计数); funnel_reject_detail(逐条被拒候选+前向收益回填); l2_reject_tracker; 拒绝原因 6 类计数(§43)",
     "已完成"),
    ("8. 市场和行业状态过滤",
     "指数趋势/宽度/风险开关",
     "E-score 生产化: F1 广度/F2 指数/F3 r20 三因子(ρ=0.924 WFO)+stale 治理+coverage 60% 门(宁缺毋滥); E 档位 coef(0.3-1.0) —— 行业相对强弱未做",
     "进行中(E✓ / 行业✗)"),
    ("9. 参数自适应路由",
     "状态识别→参数路由→样本外验证",
     "D5 Profile×Regime×Sequence 三维自适应已测并 REJECTED(判定: IS 参数拾取=噪声, flip 57%>50%); E 档位系数是已验证的自适应(§32 Δ+6.21pp) —— 状态路由部分由 E 承担",
     "已完成(否定结论+部分替代)"),
    ("10. 重建 A 股成交模型",
     "T+1/涨跌停/停牌/跳空/滑点",
     "组合层 portfolio.py 全约束(§35 表); 事件腿 paper_sim T+1/涨停拒买/停牌(§46); setup_exit 单源缺跌停(§35, Phase E #1); TTL 日历近似(§37/§49, Phase E #2); 压力测试 5/8 项(§54)",
     "进行中(Phase E 5 项待办清单在档)"),
    ("11. TP/SL 组合实验",
     "按 setup 分组比较退出模式",
     "setup_exit 单源 V1(SL=invalid−1.5ATR/TP=3R/TIME 15bar)黄金锁死; B3 宽 SL 口径预注册; TP 阶梯管理在 v0 台账(tp1-4+保本移动) —— 但系统性 TP/SL 变体对比实验未跑",
     "未开始(冻结期策略优化禁令; PAPER 30 closed 后)"),
    ("12. 逐笔交易归因",
     "market_regime/setup_type/slippage 等字段",
     "v0 台账 30+ 字段(rank/stage/adx_span/v_ratio/weekly/sub_signals/TP 阶梯, §41); PAPER 台账 escore/exposure_coef/家族/exit_status; SHADOW annotate_trade —— 审计要求的字段超集",
     "已完成"),
    ("13. Walk-forward 参数验证",
     "训练24月/验证6月/步长3月",
     "E-score ρ=0.924 WFO 已做; 事件腿 WalkForward(V1迭代4)已做; 全参数 WFO 未做",
     "进行中"),
    ("14. 影子运行与生产门槛",
     "研究→冻结→影子→纸面→小资金",
     "SHADOW 500 笔 3 倍费 PF 3.37(§29)+PAPER 7 门+G7 30closed+分档验收线(F7 假 alpha 被分层挡住, §53) —— 完整阶梯已运行; REAL MONEY 待 PAPER 累积",
     "进行中(观察期 day 8/20)"),
]

out = {"审计十二步对账": [], "汇总": {}}
done = part = no = 0
for name, crit, ev, st in STEPS:
    out["审计十二步对账"].append({"步骤": name, "验收标准": crit, "本机证据": ev, "状态": st})
    if st.startswith("已完成"):
        done += 1
    elif st.startswith("进行中"):
        part += 1
    else:
        no += 1
out["汇总"] = {"已完成": done, "进行中": part, "未开始": no, "总步骤": len(STEPS),
               "注": "未开始=冻结期策略优化禁令(用户指令) + PAPER 累积前置; 进行中=时间驱动或 Phase E 合并项"}
json.dump(out, open(r"E:\test\smc_project\research\handover\审计蓝图对账表.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"十二步对账: 已完成 {done} / 进行中 {part} / 未开始 {no} / 共 {len(STEPS)}")
for name, _, _, st in STEPS:
    print(f"  [{st[:3]}] {name[:40]}")
print("已写 handover/审计蓝图对账表.json")
# -*- coding: utf-8 -*-
"""V2 要求达成度全盘盘点(对照用户全部历史要求)
逐条核对: 已达成/部分/未达成 + 证据 commit。输出 handover/要求达成度盘点.json
"""
import io, json, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ITEMS = [
    # (编号, 要求, 状态, 证据/说明)
    ("R1", "边修改边测试边回测边验证(audit-driven)", "DONE",
     "全部18个commit均含测试+回测+验证; 327+8全绿; 每次修改先测试后提交"),
    ("R2", "V1蓝图12迭代全面审计", "DONE(核心8项)",
     "V1迭代1消融/2位移/3时序/4WF/5标注集+污染修复/6纯净三分类/7基线重生成 + 审计P0-4收口(49d9661)"),
    ("R3", "SMC结构+时序状态机(优先级①②)", "DONE(V2语义层)",
     "core/liquidity+mss+fgv_ob+displacement+structure 语义引擎完整(60+测试) + core/sequence 状态机(13测试)"),
    ("R4", "Entry+TP/SL引擎(优先级②)", "DONE",
     "core/entry.py(entry_zone/fill_in_zone)+core/risk.py(structured_tp_sl: TP1=Internal/TP2=External/TP3=HTF流动性池+无池兜底1/2/3R+EV估算) 已建; 9.8 ITERATION 7/8 25/25 测试; Zone回踩成交率 36%(321/897)——结构不及市价但 WR +9.1pp 诚实结论已出; TP/SL 池化组合层默认关闭, 止损口径(B3宽SL)在 v0/PAPER 双台账锁定"),
    ("R5", "自适应多周期引擎(优先级③)", "NOT-STARTED",
     "core/adaptive.py 仍ATR三桶(V2蓝图§28判定不足); Stock Profile/TF Selector待V2迭代5"),
    ("R6", "'一个月无新股'根因", "DONE",
     "Funnel审计: 新引擎208/月 vs 生产硬门槛33.6/月=门槛链削减84%候选(0833122)"),
    ("R7", "Funnel ±2σ 基线累积", "PARTIAL",
     "funnel_monitor.py 每日运行中; 8天累积样本待满(尚不足基线统计)"),
    ("R8", "P0-9 SMC vs EVENT 边际贡献", "DONE(欠功效)",
     "种子交集仅4-16笔→实验欠功效; 已记录待新引擎事件流重跑(3b1bc99)"),
    ("R9", "时序携带信息验证(§74)", "DONE",
     "True+0.33%>Random-0.22%>Reverse-2.56% 方向成立(7ca1f12); 诚实面: 骨架CI含0"),
    ("R10", "弱市加权k=2生产决策", "DONE",
     "WF 两轮复核一致否决 k=2(纯净8窗 k 选择: k=1×5, k=3×3, k=2×0); config.py 禁用注释完整; paper_sim 生产守卫已置 False 从未生效; tests_audit_r8i.py 锁死 WEAK_MARKET_WEIGHT=False 及守卫存在。"),
    ("R11", "AI助手基线同步纯净口径", "DONE",
     "动态JSON自动继承(d10f106); ai_assistant.py 注释已同步重基线口径(冻结2026-09-16: n=1527/avg3.77/PF3.63, OOS n=336/+4.27/PF4.03), 旧数3552已注销"),
    ("R12", "执行一致性/Replay", "DONE(工程层)",
     "统一execution内核+回测=paper同一语义; Replay逐笔重放已在b04701a完成"),
    ("R13", "亏损归因Loss Attribution", "DONE",
     "core/attribution.py 扩展为完整 20 类(原 9 类 + 新增 MFE_REVERSAL/BE_EXIT/TP_GIVEBACK/TIME_LONG/TIME_SHORT/LOW_RANK/HIGH_RANK/RANGE_HOLD/SL_STRUCTURAL/EXECUTION_COST/MEDIUM); 530 笔事件腿归因: 最大损耗=SL_TOO_WIDE 49.3%(老问题), 新分层揭示 TIME_SHORT 10.9%(入场后 <2bar SL_HIT) + RANK 高低原亏损 11.4%(rank 高分仍未避险) + MFE_REVERSAL 5.5%(曾达 1R), 已全部通过 29/29 测试。"),
    ("R14", "报告自动绑定+日历三态+入口歧义清理", "NOT-STARTED", "P2工程小项, 排后"),
    ("R15", "Stock Profile/Cluster", "NOT-STARTED", "V2迭代5"),
    ("R16", "Market Regime 正式化", "PARTIAL",
     "proxy 200股20日均(幸存者偏差已标注V2§31); 指数/Breadth/涨跌停真值未建→V2迭代6"),
]
done = [x for x in ITEMS if x[2].startswith("DONE")]
part = [x for x in ITEMS if x[2].startswith("PARTIAL")]
open_ = [x for x in ITEMS if x[2] in ("NOT-STARTED", "OPEN(证据矛盾)")]
out = {"asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
       "total": len(ITEMS), "done": len(done), "partial": len(part), "open": len(open_),
       "items": [{"id": a, "req": b, "status": c, "evidence": d} for a, b, c, d in ITEMS]}
print(f"== 要求达成度盘点 ==")
print(f"  达成 {len(done)}/{len(ITEMS)} | 部分 {len(part)} | 未达 {len(open_)}")
for a, b, c, d in ITEMS:
    print(f"  [{c:12s}] {a} {b[:34]:36s} {d[:52]}")
json.dump(out, open(r"E:\test\smc_project\research\handover\要求达成度盘点.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("\n已写 handover/要求达成度盘点.json")
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
    ("R4", "Entry+TP/SL引擎(优先级②)", "PARTIAL",
     "统一execution内核已有(TP1/2/3+SL+追踪); Entry Zone与结构化TP/SL(内/外/HTF流动性)未落地→本轮迭代7/8"),
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
    ("R10", "弱市加权k=2生产决策", "OPEN(证据矛盾)",
     "V1迭代4 WF显示k滚动不稳健(诚实降级研究保留); 但生产CFG仍启用(b4d8e35早于WF证据); 需决策"),
    ("R11", "AI助手基线同步纯净口径", "PARTIAL",
     "动态JSON已自动继承(d10f106); 注释行212仍引用n=3552旧数→本轮修"),
    ("R12", "执行一致性/Replay", "DONE(工程层)",
     "统一execution内核+回测=paper同一语义; Replay逐笔重放已在b04701a完成"),
    ("R13", "亏损归因Loss Attribution", "PARTIAL",
     "SL_GAP最贵亏损(V1迭代3)/RR_exit0.31确认TP偏近(基线冻结); 20类主因标签未建→V2迭代9"),
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
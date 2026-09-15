# -*- coding: utf-8 -*-
"""r38_frontend_sync.py —— R38 研究结果前端同步生成器.
聚合 回测/选股/复盘 三类结果 → 紧凑 JSON(E:\test\smc_project\research\r38_frontend.json),
由 web_server /api/r38 端点提供给前端面板(轮询实时同步)。
- 事件腿聚合: 从 combo_v20f_trades.csv 现算(快, ~2000行)
- 技术腿: 从 r38_tech_cache.json 加载; 缺失时全市场扫描一次并缓存(慢, ~4-5分钟)
- 复盘: 迭代日志/结论(每轮研究后由本脚本常量更新)
用法: python r38_frontend_sync.py [--rescan-tech]
"""
import csv, io, json, os, sys, bisect
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

HERE = r"E:\test\smc_project\research"
OUT = os.path.join(HERE, "r38_frontend.json")
TECH_CACHE = os.path.join(HERE, "r38_tech_cache.json")
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
RESCAN = "--rescan-tech" in sys.argv

# ---------- 指数 regime ----------
idx = json.load(open(os.path.join(HERE, "_r38_index_sh000001.json"), encoding="utf-8"))
idx.sort(key=lambda b: b["t"])
idates = [b["t"] for b in idx]; iclose = [b["c"] for b in idx]
def regime(d8):
    j = bisect.bisect_right(idates, d8) - 1
    if j < 20: return "MIX"
    ma20 = sum(iclose[j-19:j+1])/20; ma10 = sum(iclose[j-9:j+1])/10
    c = iclose[j]
    if c > ma20 and ma10 >= ma20: return "UP"
    if c < ma20 and ma10 <= ma20: return "DOWN"
    return "MIX"

def stats(pnls):
    if not pnls: return None
    w = [x for x in pnls if x > 0]; l = [x for x in pnls if x <= 0]
    pf = round(sum(w)/abs(sum(l)), 2) if sum(l) else 99
    return {"n": len(pnls), "avg": round(sum(pnls)/len(pnls), 2),
            "wr": round(100*len(w)/len(pnls), 1), "pf": pf, "sum": round(sum(pnls), 1)}

# ---------- 事件腿(冻结基线 EVENT) ----------
rows = list(csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
def f(x, d=0.0):
    try: return float(x)
    except: return d

bt = {"base": stats([f(r["net_pnl_pct"]) for r in ev])}
byy = defaultdict(list); bym = defaultdict(list); byex = defaultdict(list)
byreg = defaultdict(list); rrs = []
for r in ev:
    p = f(r["net_pnl_pct"]); d8 = r.get("entry_date") or ""
    byy[d8[:4]].append(p); bym[d8[4:6]].append(p)
    byex[r.get("reason") or "?"].append(p)
    byreg[regime(d8)].append(p)
    rr = r.get("rr_exit")
    if rr:
        try: rrs.append(float(rr))
        except: pass
bt["yearly"] = {y: stats(ps) for y, ps in sorted(byy.items())}
bt["monthly"] = {m: stats(ps) for m, ps in sorted(bym.items())}
bt["exits"] = {k: stats(ps) for k, ps in sorted(byex.items(), key=lambda kv: -len(kv[1]))[:8]}
bt["regime"] = {k: stats(ps) for k, ps in sorted(byreg.items())}
if rrs:
    bt["rr"] = {"le_m1": round(100*sum(1 for x in rrs if x <= -1)/len(rrs), 1),
                "mid": round(100*sum(1 for x in rrs if -1 < x < 1)/len(rrs), 1),
                "ge_1": round(100*sum(1 for x in rrs if x >= 1)/len(rrs), 1)}

# ---------- 技术腿 V2(量能确认) ----------
def scan_tech():
    files = sorted(fn for fn in os.listdir(KT) if fn.endswith("_daily_800.json"))
    out = []
    for path in files:
        try:
            raw = json.load(open(os.path.join(KT, path), encoding="utf-8"))
        except Exception:
            continue
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                           "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        for i in range(25, len(bs)-11):
            d = bs[i]["t"]
            if not ("20230901" <= d <= "20260831"): continue
            window = bs[max(0, i-20):i-3]
            if not window: continue
            prev_low = min(b["l"] for b in window)
            if not (bs[i]["l"] < prev_low*0.995 and bs[i+1]["c"] > prev_low and bs[i+1]["o"] > bs[i]["h"]):
                continue
            v20 = sum(b["v"] for b in bs[max(0, i-20):i])/20 if i >= 20 else 0
            if not (v20 > 0 and bs[i]["v"] > v20*1.5): continue
            ep = bs[i+1]["o"]; ex = bs[i+10]["c"]
            if ep <= 0: continue
            out.append({"s": path.split("_")[0], "d": d, "p": round((ex/ep-1)*100, 2)})
    return out

if RESCAN or not os.path.exists(TECH_CACHE):
    print("技术腿全市场扫描(首次/强制)…")
    tech = scan_tech()
    json.dump(tech, open(TECH_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"缓存 {len(tech)} 笔 → {TECH_CACHE}")
else:
    tech = json.load(open(TECH_CACHE, encoding="utf-8"))

tech_pnls = [t["p"] for t in tech]
sel = {"tech_v2": stats(tech_pnls)}
sel["pool"] = {"total_announce": 982443, "positive_events": 10151, "positive_pct": 1.1,
               "event_baseline": 1640, "tech_candidates": len(tech),
               "merged": 1640 + len(tech), "merged_per_day": round((1640+len(tech))/750, 1)}
tbyy = defaultdict(list); tbyreg = defaultdict(list)
for t in tech:
    tbyy[t["d"][:4]].append(t["p"]); tbyreg[regime(t["d"])].append(t["p"])
sel["tech_yearly"] = {y: stats(ps) for y, ps in sorted(tbyy.items())}
sel["tech_regime"] = {k: stats(ps) for k, ps in sorted(tbyreg.items())}
sel["tech_top"] = sorted(tech, key=lambda t: -t["p"])[:20]

# ---------- 两腿合并 ----------
merged_pnls = [f(r["net_pnl_pct"]) for r in ev] + tech_pnls
merged = {"combined": stats(merged_pnls), "event_pnl": bt["base"]["sum"], "tech_pnl": sel["tech_v2"]["sum"]}
mreg = defaultdict(list)
for r in ev: mreg[regime(r.get("entry_date") or "")].append(f(r["net_pnl_pct"]))
for t in tech: mreg[regime(t["d"])].append(t["p"])
merged["regime"] = {k: stats(ps) for k, ps in sorted(mreg.items())}

# ---------- 复盘(迭代日志, 每轮研究后更新) ----------
review = {
    "verdicts": [
        {"id": "A1", "name": "缠论3买分层(事件腿)", "result": "证伪",
         "detail": "3买型 avg+1.26/PF1.82 < 非3买 +3.92/3.45 —— 事件驱动≠趋势突破"},
        {"id": "B1", "name": "Wyckoff spring 止损", "result": "证伪",
         "detail": "70%触发但 avg-0.14pp —— 收紧SL打掉回摆单"},
        {"id": "C1", "name": "指数UP-regime过滤", "result": "修正废弃",
         "detail": "生产_market_proxy分桶: 弱市信号最好(PF3.98) —— C1方向相反, 2024-25通过是样本巧合"},
        {"id": "V2", "name": "技术腿量能确认(10日持有)", "result": "降级——未过稳健检验",
         "detail": "10日持有 PF2.63 看似可用; 但套事件腿SL口径仅PF2.02(41%几何非法), "
                   "独立SL搜索最优PF5.26 经 IS/OOS 检验 IS 7.96→OOS 0.99(比0.12) 严重过拟合"},
        {"id": "TECH-VERIFY", "name": "技术腿最优变体稳健性", "result": "否决",
         "detail": "IS n=1824 +7.76%/PF7.96 vs OOS n=500 -0.04%/PF0.99; PF5.26 全靠 2024"
                   "(MIX×2024 PF29.7) 单年产物; 逐年最稳实为 DOWN 桶(3.6/3.1/2.4/1.1), "
                   "非 MIX —— 技术腿不得接线生产"},
        {"id": "MERGE", "name": "两腿合并", "result": "互补确认(但技术腿需重做)",
         "detail": "事件腿吃UP(PF5.54), 技术腿吃MIX(PF7.13聚合值) —— 但技术腿MIX优势 "
                   "经逐年交叉验证为 2024 单年假象, 合并结论待技术腿口径重做后复核"},
        {"id": "预增扩池", "name": "业绩预增事件(扩池候选)", "result": "❌ 否决(同口径错配)",
         "detail": "裸20日持有 +5.15%/PF3.02(IS2.58→OOS3.56)看似可用; 但 gen_v20f "
                   "同口径后 n=88 avg-0.87% PF0.68 (2024 -3.48%/PF0.22), RR<=-1R 45.5%。"
                   "根因: 业绩预增是动量事件(赢家在MARKUP), 基线过滤器只要ACCUM/DOWNTREND "
                   "(超跌股) → 选中错误子集(利好出尽)。适配性必须在目标策略口径下验证。"},
        {"id": "预减否决", "name": "业绩预减事件", "result": "❌ 否决(退市偏差)",
         "detail": "缺失主板股 41.9% 含退市公告(vs 对照股东增持21.1%/回购8.8%); "
                   "'正收益'纯属幸存者偏差 —— 被剔除的正是退市下跌股"},
        {"id": "激励观察", "name": "股权激励授予", "result": "⚠ 降级观察",
         "detail": "OOS PF1.61(比0.93)但缺失率61.7% + 2026 -1.99%; 样本不足以采信"},
        {"id": "STAGE-RELAX", "name": "stage白名单放宽", "result": "❌ 否决(验证白名单正确)",
         "detail": "全stage同口径: ACCUM PF3.86(OOS6.87)/DOWNTREND PF3.09(OOS2.95) ✅; "
                   "UPTREND PF1.09(OOS1.17)/MARKUP 1.88(OOS0.96) ❌。放宽+53%量但PF 3.21→2.41, "
                   "增量全是零edge的UPTREND。现有白名单是正确设计, 非保守惯性"},
        {"id": "SCARCE-ROOT", "name": "选股量少的本质", "result": "内在属性(非可修缺陷)",
         "detail": "扩池三连否(技术腿OOS0.99 / 业绩预增同口径0.68 / stage放宽1.09-1.88)证明: "
                   "alpha 高度集中在'内部人事件×超跌反转'窄带, 任何方向扩量只引入零/负期望。"
                   "正解=接受供给约束+把质量与资金效率做到极致"},
        {"id": "ACCUM-CORE", "name": "ACCUM 核心精选仓位", "result": "✅ 温和正面(非突破)",
         "detail": "ACCUM×2: PF 3.21→3.29, 累计 +5766→+6913%, 但 MDD -760→-876; "
                   "ACCUM×3: PF3.36/累计+8061%/MDD-992。仅ACCUM: PF3.86/MDD-118(敞口仅15%)。"
                   "按敞口归一后 MDD 近似 —— 优势在每单位收益(+4.72% vs +3.52%), 非风险更低。"
                   "2025-2026 显著改善(A+4.37→D+7.36), 但与 R38k OOS 同源, 非独立验证"},
        {"id": "RANK-PATH", "name": "rank 分层加权", "result": "❌ 无效(路径关闭)",
         "detail": "E方案 rank/4 加权: PF 3.19 vs 等权 3.21 —— 零改善; F方案 ACCUM×2×rank闸 "
                   "累计降至 +3527(rank<4 减半损失过大)。rank 不是有效分层变量"},
        {"id": "EXIT-SWEEP", "name": "退出参数扫描(7配置)", "result": "现有退出局部最优",
         "detail": "D长持有20 全样本PF3.26最高但OOS 3.33最差(不稳健); E无部分止盈 avg+4.44% "
                   "但MDD恶化43%; F/G 与基线持平。退出结构已局部最优, 不采纳D"},
        {"id": "P1-8-RESOLVED", "name": "审计P1-8分叉解决(15 vs 12)", "result": "✅ 生产口径更稳健",
         "detail": "B生产口径(max_hold=12): 全样本PF3.11略低, 但 **OOS PF4.41最高 + MDD-630最优**。"
                   "生产口径以小幅IS损失换OOS稳健性与回撤控制 —— 分叉不是缺陷, 保持CFG.MAX_HOLD=12"},
        {"id": "P1-7-FOUND", "name": "P1-7 ADX 分叉量化", "result": "⭐ 首个可改进基线的修复",
         "detail": "旧版单窗DX 双向出错: 错杀610笔好票(avg+4.15%/PF4.01) + 误收979笔差票"
                   "(+1.19%/PF1.71)。切到 Wilder ADX: 池 n 1642→1547(-6%), avg +3.50→+4.56%, "
                   "PF 3.19→4.03 —— 纯质量提升。需走完整审计(冻结线变更), 不得直接改 gen_v20f.py"},
        {"id": "P1-7-MECH-FIX", "name": "P1-7 注释方向复核", "result": "⚠ 机制描述修正(结论仍成立)",
         "detail": "core/indicators.py 注释'旧单窗DX系统性偏低'经 fixture 复核**不成立**: "
                   "合成序列两版几乎一致; 真实数据 n=120 Wilder-legacy 中位 -3.66(Wilder更低); "
                   "通过率 legacy 65.0% > Wilder 56.7%(旧版通过更多)。正确机制=旧版判定**噪声大**"
                   "(双向出错), 非'偏低导致门过严'。但核心结论(Wilder更好)仍成立 —— 证据是"
                   "R38n 质量分析(PF3.19→4.03), 非通过率。建议修正注释(文档改动, 不改逻辑)"},
        {"id": "R38-CONVERGE", "name": "R38 迭代收敛判断(修正)", "result": "收敛点已修正",
         "detail": "13轮: 扩池三连否 + stage/rank/退出验证现状 + P1-8解决 + **P1-7确认可改进**。"
                   "结论修正为: 基线的 ADX 实现有已知缺陷, 修复后可提升核心池质量 —— "
                   "比扩池更根本的杠杆"},
    ],
    "production": [
        "生产 _market_proxy 弱市加仓机制正确保持(已验证 PF3.20→3.64) —— 唯一确认的生产机制",
        "技术腿: 未经稳健检验前**不得接线**(最优变体 OOS PF0.99 = 零 edge)",
        "业绩预增: 同口径 PF0.68 否决 —— 与基线 stage 过滤器(ACCUM/DOWNTREND)错配(利好出尽)",
        "stage 放宽: 否决 —— 现有白名单(ACCUM/DOWNTREND)经 OOS 验证为正确设计, 非保守惯性",
        "退出参数: 现有结构局部最优 —— 保持 CFG.MAX_HOLD=12(生产口径 OOS PF4.41/MDD-630 最优); "
        "审计 P1-8 分叉已解决(非缺陷)",
        "唯一待接线候选: ACCUM×2 温和加权(PF 3.21→3.29) —— 需走 paper_sim 完整审计",
        "⭐ P1-7 修复: 基线切到 Wilder ADX 可提升核心池质量(avg+1.06pp/PF+0.84) —— "
        "需走完整审计(冻结线变更: 重跑全事件回测+全测试链+冻结基线重认定)",
        "注: 需复核 core/indicators.py 注释'旧版偏低'与实际差值方向(实测旧版偏高)的一致性",
        "扩池三连否: 技术腿(0.99) / 业绩预增(0.68) / stage放宽(1.09-1.88) —— "
        "'选股量少'是 alpha 内在属性(内部人事件×超跌反转窄带), 不可通过扩量修复",
        "下一轮: ①ACCUM 核心精选仓位优化(OOS PF6.87 最强子集) ②rank×仓位联合优化",
    ],
    "iterations": [
        {"round": "R38a", "commit": "351ebd8", "content": "三维复盘+多学派诊断+A1/B1证伪+C1初验"},
        {"round": "R38b", "commit": "017f964", "content": "C1敏感性+组合闸+候选池边界"},
        {"round": "R38c", "commit": "5535160", "content": "仓位缩放+2026特异性+技术腿可行性"},
        {"round": "R38d", "commit": "9f673a3", "content": "C1修正废弃(生产proxy正确)+量能闸验证+000157断言状态化"},
        {"round": "R38e", "commit": "7fbae53", "content": "两腿合并评估(信号×环境互补)"},
        {"round": "R38f", "commit": "09dab0f", "content": "前端同步(回测/选股/复盘面板 + /api/r38 实时轮询)"},
        {"round": "R38g", "commit": "4255d95", "content": "技术腿同口径回测(41%几何非法)+regime系数验证(适配成立)"},
        {"round": "R38h", "commit": "318f50f", "content": "技术腿独立SL/TP搜索(PF5.26)→IS/OOS检验 OOS PF0.99 否决"},
        {"round": "R38i", "commit": "b655dd6", "content": "事件腿扩池: 业绩预增晋级(裸持有)/业绩预减否决(退市偏差41.9%)"},
        {"round": "R38j", "commit": "7077c2f", "content": "业绩预增同口径回测: PF0.68 否决(与ACCUM/DOWNTREND过滤错配)"},
        {"round": "R38k", "commit": "6001498", "content": "stage白名单放宽: 否决(UPTREND PF1.09/MARKUP OOS0.96); 现有白名单验证正确"},
        {"round": "R38l", "commit": "d6813e2", "content": "ACCUM核心精选仓位: 温和正面(PF3.21→3.29); rank加权无效(路径关闭)"},
        {"round": "R38m", "commit": "9c42d9e", "content": "退出参数扫描(7配置): 现有退出局部最优; 审计P1-8分叉解决(生产12 OOS最优)"},
        {"round": "R38n", "commit": "4919b00", "content": "P1-7 ADX分叉量化: 旧版单窗DX双向出错; Wilder修复提升核心池(avg+1.06pp/PF+0.84)"},
        {"round": "R38o", "commit": "-", "content": "P1-7注释方向复核: '系统性偏低'不成立(实测Wilder更低); 机制修正为'旧版噪声大', 结论仍成立"},
    ],
    "schools": {"ICT/SMC": 1250, "PriceAction": 229, "ChanLun缠论": 110, "Indicator": 214,
                "OrderFlow": 34, "Volume/VSA": 10, "Wyckoff": 5, "ElliottWave": 8, "TheStrat": 4},
}

data = {"updated": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "backtest": bt, "selection": sel, "merged": merged, "review": review}
json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"→ {OUT} ({os.path.getsize(OUT)} bytes)")
print(f"  事件腿 n={bt['base']['n']} PF={bt['base']['pf']} | 技术腿 n={sel['tech_v2']['n']} PF={sel['tech_v2']['pf']}")
print(f"  合并 n={merged['combined']['n']} avg={merged['combined']['avg']}%")

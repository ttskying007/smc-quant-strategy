# -*- coding: utf-8 -*-
r"""r38_frontend_sync.py —— R38 研究结果前端同步生成器.
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

# ---------- V699 冻结回放(研究链, 独立于生产回测块) ----------
V699_LATEST = r"E:\root\.hermes\smc_audit\v699_pure_smc_ssl_reclaim_replay_latest.json"

def v699_block():
    try:
        r6 = json.load(open(V699_LATEST, encoding="utf-8"))
    except Exception as e:
        print(f"V699 latest 不可用({e}) -> v699_replay 块省略(fail-closed)")
        return None
    def st(d):
        if not d: return {"n": 0, "avg": 0.0, "wr": 0.0, "pf": 0.0, "sum": 0}
        return {"n": d.get("n", 0), "avg": d.get("avg_net_pnl_pct", 0.0),
                "wr": d.get("gross_wr_pct", 0.0), "pf": d.get("profit_factor", 0.0),
                "sum": d.get("total_net_pnl_pct", 0)}
    ov = r6.get("overall") or {}
    mtg = r6.get("monthly_trade_count_gate") or {}
    return {
        "title": "V699 纯SMC SSL扫荡回收 冻结线 T+1 严格回放(研究链)",
        "label": "研究链结果: 因果工程通过(oracle身份一致/不变量全绿)但经济性失败 -> fail-closed(审计§12)",
        "decision": r6.get("decision"),
        "promotion_gate_pass": r6.get("promotion_gate_pass"),
        "production_write": r6.get("production_write"),
        "generated_at": r6.get("generated_at"),
        "seed_count": r6.get("seed_count"),
        "closed_trade_count": r6.get("closed_trade_count"),
        "contract": r6.get("frozen_execution_contract"),
        "base": st(ov),
        "yearly": {y: st(d) for y, d in sorted((r6.get("yearly") or {}).items())},
        "exits": ov.get("exit_counts") or {},
        "skip_counts": r6.get("nontradable_or_serial_skip_counts") or {},
        "gate_checks": r6.get("promotion_checks") or {},
        "invariants": r6.get("invariants") or {},
        "monthly_gate_failed_months": mtg.get("failed_months_n<=4") or [],
        "note": "本块为 V697-V699 研究链严格回放, 与 backtest 块(R38 EVENT 腿, canonical 生产策略回测)是两条不同管线; 前端须区分展示, 不得混用口径",
    }

v699b = v699_block()

# ---------- V700 生产扫描器(承诺 epoch 当前漏斗) ----------
V700_LATEST = r"E:\root\.hermes\smc_audit\v700_pure_smc_ssl_reclaim_current_scanner_latest.json"

def v700_block():
    try:
        r7 = json.load(open(V700_LATEST, encoding="utf-8"))
    except Exception as e:
        print(f"V700 latest 不可用({e}) -> v700_scanner 块省略(fail-closed)")
        return None
    fun = (r7.get("diagnostic_funnel") or {}).get("counts") or {}
    dfun = r7.get("diagnostic_funnel") or {}
    return {
        "title": "V700 生产扫描器 承诺epoch当前漏斗(诊断用途, 非可交易订单)",
        "label": "审计§8: 当前漏斗逐层计数; partial 行为 outcome-blind 诊断, 不得作为订单",
        "generated_at": r7.get("generated_at"),
        "epoch_id": r7.get("epoch_id"),
        "market_date": r7.get("market_date"),
        "files_seen": r7.get("files_seen"),
        "files_on_committed_date": r7.get("files_on_committed_date"),
        "admission_eligible": r7.get("admission_eligible"),
        "pending_next_open_count": r7.get("pending_next_open_count"),
        "buy_valid_count": r7.get("buy_valid_count"),
        "funnel": fun,
        "full_current_setup_count": dfun.get("full_current_setup_count"),
        "release_blocker": dfun.get("release_blocker"),
        "blocked_by": r7.get("blocked_by") or {},
        "decision": r7.get("decision"),
        "invariants": r7.get("invariants") or {},
    }

v700b = v700_block()

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
         "detail": "10日持有 PF2.63 看似可用; 但套事件腿SL口径仅PF2.02(41%几何非法), 独立SL搜索最优PF5.26 经 IS/OOS 检验 IS7.96→OOS0.99(比0.12) 严重过拟合"},
        {"id": "TECH-VERIFY", "name": "技术腿最优变体稳健性", "result": "否决",
         "detail": "IS n=1824 +7.76%/PF7.96 vs OOS n=500 -0.04%/PF0.99; PF5.26 全靠 2024(MIX×2024 PF29.7) 单年产物; 逐年最稳实为 DOWN 桶 —— 技术腿不得接线生产"},
        {"id": "MERGE", "name": "两腿合并", "result": "互补确认(但技术腿需重做)",
         "detail": "事件腿吃UP(PF5.54), 技术腿吃MIX(PF7.13聚合值) —— 技术腿MIX优势经逐年交叉验证为 2024 单年假象"},
        {"id": "预增扩池", "name": "业绩预增事件(扩池候选)", "result": "否决(同口径错配)",
         "detail": "裸20日持有 +5.15%/PF3.02 看似可用; gen_v20f 同口径后 n=88 avg-0.87% PF0.68 (2024 -3.48%), RR<=-1R 45.5%。根因: 业绩预增是动量事件, 基线过滤器要 ACCUM/DOWNTREND(超跌股) → 选中错误子集"},
        {"id": "预减否决", "name": "业绩预减事件", "result": "否决(退市偏差)",
         "detail": "缺失主板股 41.9% 含退市公告(vs 对照股东增持21.1%/回购8.8%); '正收益'纯属幸存者偏差"},
        {"id": "激励观察", "name": "股权激励授予", "result": "降级观察",
         "detail": "OOS PF1.61(比0.93)但缺失率61.7% + 2026 -1.99%; 样本不足以采信"},
        {"id": "STAGE-RELAX", "name": "stage白名单放宽", "result": "否决(验证白名单正确)",
         "detail": "ACCUM PF3.86(OOS6.87)/DOWNTREND PF3.09(OOS2.95) 优; UPTREND PF1.09(OOS1.17)/MARKUP 1.88(OOS0.96) 差。放宽+53%量但 PF 3.21→2.41, 增量全是零edge的UPTREND"},
        {"id": "SCARCE-ROOT", "name": "选股量少的本质", "result": "内在属性(非可修缺陷)",
         "detail": "扩池三连否(技术腿OOS0.99 / 业绩预增同口径0.68 / stage放宽1.09-1.88)证明 alpha 高度集中在'内部人事件×超跌反转'窄带; 正解=接受供给约束+把质量与资金效率做到极致"},
        {"id": "ACCUM-CORE", "name": "ACCUM 核心精选仓位", "result": "温和正面(非突破)",
         "detail": "ACCUM×2: PF 3.21→3.29, 累计 +5766→+6913%, MDD -760→-876。仅ACCUM: PF3.86/MDD-118(敞口仅15%)。按敞口归一后 MDD 近似, 优势在每单位收益(+4.72% vs +3.52%)"},
        {"id": "RANK-PATH", "name": "rank 分层加权", "result": "无效(路径关闭)",
         "detail": "E方案 rank/4 加权 PF3.19 vs 等权 3.21 —— 零改善; F方案累计降至+3527。rank 不是有效分层变量"},
        {"id": "EXIT-SWEEP", "name": "退出参数扫描(7配置)", "result": "现有退出局部最优",
         "detail": "D长持有20 全样本PF3.26最高但OOS 3.33最差(不稳健); E无部分止盈 avg+4.44% 但MDD恶化43%; F/G 与基线持平"},
        {"id": "P1-8-RESOLVED", "name": "审计P1-8分叉解决(15 vs 12)", "result": "生产口径更稳健",
         "detail": "B生产口径(max_hold=12): 全样本PF3.11略低, 但 OOS PF4.41最高 + MDD-630最优 —— 分叉不是缺陷, 保持CFG.MAX_HOLD=12"},
        {"id": "P1-7-FOUND", "name": "P1-7 ADX 分叉量化", "result": "首个可改进基线的修复",
         "detail": "旧版单窗DX 双向出错: 错杀610笔好票(avg+4.15%/PF4.01) + 误收979笔差票(PF1.71)。切Wilder: 池 n1642→1547(-6%), avg +3.50→+4.56%, PF 3.19→4.03"},
        {"id": "P1-7-MECH-FIX", "name": "P1-7 注释方向复核", "result": "机制描述修正(结论仍成立)",
         "detail": "core/indicators.py 注释'旧单窗DX系统性偏低'经 fixture 复核不成立: 真实数据 n=120 Wilder-legacy 中位 -3.66(Wilder更低); 通过率 legacy 65.0% > Wilder 56.7%。正确机制=旧版判定噪声大(双向出错)。注释已修正(36b4e71, 回归62库全绿)"},
        {"id": "WILDER-REBASE", "name": "P1-7 Wilder 重基线 A/B", "result": "四项判据全过(晋级)",
         "detail": "独立分叉同口径 A/B (n 1974→1861): 胜率 61.3→64.4% | avg +3.83→+4.60% | PF 3.08→3.56 | MDD -629→-490 | RR<=-1R 23.5→20.6%。IS PF 2.90→3.65, OOS 3.48→3.36(非劣化)。冻结线变更需走完整审计"},
        {"id": "P1-7-AUDIT", "name": "P1-7 审计路径确认", "result": "性质=回测追上生产(风险下调)",
         "detail": "决定性确认: 生产 paper_sim.py L314-321 的 adx14_of 是兼容入口, 委托 core.indicators.adx14_of(Wilder); L744-745 EVENT 腿门 = Wilder ADX>=20 —— 生产早已在用 Wilder。故重基线='让回测追上生产', 生产行为零变化, 审计风险 中→低"},
        {"id": "REBASE-MERGE", "name": "P1-7+P1-8 合并重基线证据包", "result": "最佳合并口径=Wilder+h12",
         "detail": "一次扫描两口径: 冻结基线 n=1974/PF3.08/MDD-629 | Wilder h15 n=1547/PF4.04/MDD-482 | Wilder h12(生产口径) n=1547/PF3.72/MDD-448/OOS PF4.03。h12 MDD最优+OOS最高+2026最强(+4.87/4.41)+RR左尾最低(19.2%)。两分叉一次性统一; 待用户批准后走完整审计"},
         {"id": "REBASELINE-DONE", "name": "P1-7+P1-8 合并重基线(已执行)", "result": "✅ 已完成(用户批准)",
          "detail": "2026-09-16 执行完整审计: 归档 legacy(DX+h15, n=1974/PF3.08/MDD-629) + "
                    "新生成器 gen_v20f2_wilder_h12.py + 重认定(新认证 EVENT n=1527 avg+3.767% PF3.63, "
                    "OOS PF4.03) + 逐笔核对(0 mismatch; 20 笔差额=月度cap挤出) + 全测试链。 "
                    "canonical combo_v20f_trades.csv 已接管新基线, 139 处消费方(含生产)自动生效。 "
                    "性质=让回测追上生产, 生产行为零变化"},
         {"id": "RANK-OOS", "name": "rank 门槛 IS/OOS 验证", "result": "✅ 唯一通过稳健检验的信号层候选",
          "detail": "C rank>=3: IS PF3.94→OOS PF4.41(比1.12) 保留89%; "
                    "D rank>=4: IS PF4.29→OOS PF4.39(比1.02) 保留62%, OOS MDD-54(vs等权-115); "
                    "E rank>=5: OOS PF3.00(比0.70) ❌ 过严反而劣化 → 存在真实最优点。 "
                    "逐年: 2024 +3.93→+4.53 / 2026 +4.87→+5.40 改善; 2025 +2.26→+2.14 轻微劣化(n=70)"},
         {"id": "RANK-CHAIN", "name": "rank 门槛全链路审计(最终)", "result": "✅ 确认 >=3(数字修正)",
          "detail": "完整选择链重放(非CSV离线过滤): EVENT-only gate>=3 = IS PF3.77 / **OOS PF4.33** "
                    "(R38x 的 4.52 无法复现 — 根因: R38x 在已过cap的1527笔上过滤, 全链路在过滤后才cap)。 "
                    "**gate>=3 �� >=4 的 OOS PF 几乎相同(4.33 vs 4.32), 但 >=3 多保留 41% 交易** → >=3 严格更优。 "
                    "**隐藏耦合**: >=4 的亮眼数字只在同时删掉整个CONT腿时成立; 保留CONT则OOS反降至3.58(≈基线)。 "
                    "CONT腿复核: OOS n=194 avg+6.79% PF3.21 → 非拖累, 应保留。 "
                    "**最终推荐: rank_prod>=3, 仅作用于EVENT腿, CONT不动** "
                    "(EVENT OOS PF 4.03→4.33 保留89%; 组合 OOS 3.57→3.67)。 "
                    "自检: 分解脚本E/F标签写反(数字正确, 结论按真实语义重述)"},
         {"id": "RANK3-VERIFY", "name": "rank3 研究分叉验收", "result": "✅ 与全链路审计逐项一致",
          "detail": "r38_gen_v20f_rank3.py = 基线生成器 + 仅两处增量(补齐生产2项增持特征 + "
                    "EVENT腿 rank>=3 门槛), 输出独立文件不碰 canonical。 "
                    "验收: 全组合 n=1735(与审计 Δ=0) | IS n=1243/PF3.44 | OOS n=492/PF3.67 —— 逐项匹配。 "
                    "EVENT 腿 rank 分布 {3:334,4:476,5:342,6:169,7:67,8:13,9:1}, 低于门槛 0 笔。 "
                    "vs 基线: n 1861→1735(-126), avg +4.054→**+4.297%**, PF 3.35→**3.52**, MDD -415→**-383**; "
                    "逐年 2024 +3.89→+4.12/PF3.44→3.65, 2025 +3.08→+3.28, 2026 +5.85→+6.17/PF4.38→4.59 全部改善。 "
                    "**接线证据就绪**(双路径交叉验证: 独立实现 + 完整链重放完全一致)"},
         {"id": "RANK3-WIRED", "name": "rank>=3 生产接线(已执行)", "result": "✅ 已生效(用户批准)",
          "detail": "2026-09-16 执行。仅 2 文件改动: ① config.py 新增开关 "
                    "EVENT_RANK_GATE_MIN(默认3, SMC_EVENT_RANK_GATE_MIN 可覆盖, =0 一键回滚) "
                    "② paper_sim.py EVENT腿加门槛(位置: rank_score 全特征之后 / 仓位计算之前)。 "
                    "拒绝路径完整可观测(漏斗+明细+拒绝台账)。新增 tests_audit_r38_rank_gate.py "
                    "(26项全绿, 含离线重放: 候选1547→通过1405→分叉EVENT 1402)。 "
                    "全量回归 62库 1299 PASS / 0 FAIL。预期 PF 3.35→3.52 / OOS 3.57→3.67 / MDD -415→-383"},
         {"id": "GATE-MONTHLY", "name": "门槛×月度检验(修正版)", "result": "门槛未修好弱势月",
          "detail": "用 cap 前全集(1547笔带真实rank)纯 rank 切分(修正上版混淆门槛/cap的缺陷): "
                    "4月 -0.80→-0.11%/0.73→0.96(仍负) | 5月 -1.42→-1.64%/0.53→0.54(仍负) | "
                    "6月 **-0.80→-1.23%/0.70→0.57(变差!)** —— 6月被剔除的17笔 avg+1.86%/PF2.19 是赚钱的。 "
                    "全集亏损月{01,04,05,06,12}→门槛后{01,04,05,06,11,12}; 修好:无, 弄坏:11月。 "
                    "→ 4/5/6月弱势是**独立季节性问题**, 通用质量闸无法解决; 季节性规避须单独过 IS/OOS"},
         {"id": "GATE-CHARACTER", "name": "门槛定性修正(重要)", "result": "质量换数量, 非剔除垃圾",
          "detail": "被门槛剔除的 142 笔整体是**赚钱的**: n=142 avg=**+2.17%** PF=**2.32**。 "
                    "门槛后 n=1405 avg+4.02%/PF3.89 | 全集 n=1547 avg+3.85%/PF3.72。 "
                    "→ 门槛**不是砍掉差票, 而是砍掉低于池子均值的票**: 提升每单位资金效率 "
                    "(avg+0.17pp/PF+0.17), 代价是放弃一批正期望交易。 "
                    "→ **资金充裕/追求绝对收益的场景, 保留全部1547笔累计收益可能更高**; "
                    "门槛更适合资金受限或追求风险调整收益的场景。此点应写入接线说明避免误读"},
         {"id": "RANK-SIZING", "name": "rank 作仓位权重 vs 硬门槛", "result": "❌ 假设证伪",
          "detail": "假设(源自R38af): 门槛剔的是赚钱票 → 改加权可能更优。检验(cap前1547笔): "
                    "B硬门槛 每单位+4.017%/PF3.89/MDD-418 (最优) | C线性 3.951/3.81 | D温和 3.967/3.85/-595 | "
                    "E阶梯 3.934/3.80/-618。 **D/E 累计更高(+8255/+8346 vs B+5644)纯属敞口放大**: "
                    "敞口比 2081/1405=1.48x, 累计比 8255/5644=1.46x —— 几乎同比例; 归一后 D 3.967%<B 4.017%, "
                    "OOS 亦然(4.356 vs 4.569)。 → **硬门槛仍最优, 加权=变相加杠杆**"},
         {"id": "EXPOSURE-NORM", "name": "敞口归一方(方法论)", "result": "⚠ 评估仓位改动必用",
          "detail": "本轮若不归一, 会误判 D(温和加权)优于硬门槛 —— 实际其优势 100% 来自敞口放大。 "
                    "**评估任何仓位/加权类改动, 必须用「每单位敞口收益」(avg_exp)而非累计收益**; "
                    "累计收益只反映杠杆水平, 不反映 edge 是否改善。 "
                    "同法审视 R38l ACCUM×2(其表面收益亦多来自敞口)。"},
         {"id": "SEASONALITY", "name": "月度季节性规则 IS/OOS", "result": "否决(多重检验)",
          "detail": "日期切分有结构性缺陷(月份与切分耦合): 04月 OOS=0 / 07月 IS=0 / 05,12月 OOS=5。 "
                    "改用逐年交叉验证: skip-6 表面 3/3 年改善(3.64→4.02 | 3.19→3.37 | 4.41→6.37), "
                    "但多重检验校正后**不成立**: 检验12月, 期望 1.5 月随机达 3/3, 实测 1 个; "
                    "置换检验(打乱月份标签500次) p≈**0.788** 远大于 0.05。 "
                    "机制: 2025年6月为正(+1.61%/PF2.34) → 规则实为「剔除低于均值的月」, 属事后选择"},
         {"id": "WEAK-MONTH-CORRECT", "name": "「4/5/6月恒亏」修正", "result": "证据不足(下调R38u)",
          "detail": "逐年样本: 04月 2024 n=36 / 2025 n=1 / 2026 n=0; 05月 2024 n=38 / 2025 n=0 / 2026 n=5。 "
                    "→ 4/5月的弱势几乎全来自 **2024 单年**; 只有 6 月有真跨年样本(n=44/28/50)。 "
                    "且 **无任何月份在 3 年中全部为负**。 "
                    "→ R38u 的「4/5/6月恒亏是真实季节性弱点」应下调为: 2024年4/5/6月偏弱; "
                    "6月跨年偏弱但2025为正; **无稳定季节性**"},
         {"id": "MT-DISCIPLINE", "name": "多重检验纪律(方法论)", "result": "新增通用规则",
          "detail": "两条新规则: (1)季节性/分组类规则**必须用逐年交叉验证** —— 日期切分 IS/OOS "
                    "与月份耦合, 会制造虚假通过(本轮04月OOS=0仍被标为通过)。 "
                    "(2)检验多个候选(月份/参数/分组)**必须做多重检验校正** —— 否则把噪声当选信号 "
                    "(期望假阳性数 = 候选数 x 单次显著性水平)。与 R38h/C1 同类收敛。"},
         {"id": "RESEARCH-DISCIPLINE", "name": "研究纪律手册(R38沉淀)", "result": "已归档 23 条",
          "detail": "handover/研究纪律手册.md (6984 字节, 5 章 19 条), 每条附**具体失败案例**。 "
                    "章节: 一验证设计(R1-R5) / 二归因统计(R6-R9) / 三接线运维(R10-R14) / "
                    "四记录诚实(R15-R19) / 五新假设标准流程(10 步清单)。 "
                    "关键规则: 预注册判据 / 逐年交叉验证 / 多重检验校正 / 全链路重放 / "
                    "敞口归一 / 隐藏耦合 / 生效性验证(进程mtime) / 一键回滚 / 记录证伪。 "
                    "价值: 把 R38 三十轮的代价教训变成后续会话可直接复用的检查清单"},
         {"id": "ACCUM-NORM", "name": "ACCUM x2 敞口归一复核", "result": "形式通过(非纯杠杆)",
          "detail": "R38l 未做归一, 本轮补做(R38ah 规则R6): 敞口 1527->1789(1.17x), "
                    "每单位敞口收益 +3.767->+3.907%(+0.140pp), PF 3.63->3.74, MDD -408->-458。 "
                    "-> 通过归一: 优势不是纯杠杆 -- 与 R38ah rank 加权(归一后劣化)定性不同"},
         {"id": "ACCUM-YEARLY", "name": "ACCUM x2 逐年分解", "result": "降级观察项(不接线)",
          "detail": "IS 3.626/3.52->3.563/3.45(劣化) | OOS 4.266/4.03->4.986/4.75(大幅改善) "
                    "-> 改善全集中OOS。逐年: 2023劣化 | 2024劣化(ACCUM n=149 最大样本) | "
                    "2025改善(n=17) | 2026改善(n=91)。 2024年 ACCUM 子集 +2.99%/PF2.79 "
                    "明显劣于 非ACCUM +4.09%/PF3.81 -- 最强反向证据。 "
                    "-> 改善集中于最近两年(与R38k同源), 属时间趋势非跨期稳定 -> 不接线, 保留观察"},
         {"id": "THREE-CASES", "name": "候选三情形定性(R38方法论)", "result": "首次明确区分",
          "detail": "(1) rank加权(R38ah): 归一后劣化 -> 纯杠杆, 无价值 | "
                    "(2) ACCUM x2(本轮): 归一后通过但仅近2年 -> 有非杠杆价值但不稳健 | "
                    "(3) Wilder重基线(R38s): 全期一致 -> 口径修正, 已执行。 "
                    "-> 首次明确区分中间状态: 有价值但稳健性不足, 处置=记录在案不接线"},
         {"id": "ACCUM-DISCRIM", "name": "ACCUM x2 判别变量搜索", "result": "条件化也不可靠",
          "detail": "搜索 signal 日可得特征使 ACCUM x2 在 2024 也不劣化: ACCUM & ret60<=-0.25 "
                    "(命中116/1527) 看似可救(2024/2025/2026 全改善)。2024 ACCUM 内部细分证实: "
                    "ret60<=-0.25 n=63 **avg+5.864%/PF5.44**(优于非ACCUM+4.09%); ret60>-0.25 n=86 仅 +0.879%/PF1.46。 "
                    "→ 深度超跌子集才是好票"},
         {"id": "ACCUM-REJECT", "name": "ACCUM x2 敏感性检验", "result": "否决(维持观察项)",
          "detail": "**该阈值是看着2024挑的, 必须做敏感性扫描**: 切点 -0.35..-0.15 (21个): "
                    "3年全改善的仅 -0.25..-0.21 (**跨度仅0.04, 不达0.05判据**), 双侧迅速失效(窄峰)。 "
                    "**多重检验**: 21切点期望随机达标 2.62 个, 实测 5 个 → 未显著。 "
                    "**置换检验**: 打乱ret60 200次, 14.5% 的随机标签也能产生>=5个达标 → **p≈0.145 不显著**。 "
                    "→ **与 R38ai(季节性)同型: 事后选择阈值, 聚合数字好但缺跨期稳健性**。ACCUM x2 研究线收束(3轮)"},
         {"id": "THRESH-DISCIPLINE", "name": "阈值型规则纪律(方法论)", "result": "强化 R3/R19",
          "detail": "本轮新增两条: (1)**阈值型规则必须做敏感性扫描** —— 单点有效 != 规则有效, 需**连续区间**支撑; "
                    "(2)**看着子样本挑阈值必触发多重检验** —— 本轮 21 个切点期望 2.62 个随机达标。 "
                    "正确做法: 先扫描(而非只报最优点)再做置换 —— 只有这样才能区分真实区间与窄峰噪声。 "
                    "若只跑单点会误判为可接线候选"},
         {"id": "EXIT-FIELD", "name": "出场字段发现", "result": "mae_r/mfe_r 可用",
          "detail": "CSV 含 mae_r/mfe_r(最大不利/有利偏移, R计) 与 risk_pct(止损距离) "
                    "-- 逐笔分析的直接证据, 此前未被利用。止损距离中位 **11.88%** (p75 27.53%) "
                    "-> 止损极宽, 远超典型短线策略"},
         {"id": "STOP-NOT-CAUSE", "name": "扫损检验(止损是否主因)", "result": "止损**不是**主因",
          "detail": "SL_HIT n=232 的 **mfe_r 中位仅 0.304** (< 0.5 判据) -> 59.9% 被打掉前浮盈<=0.5R "
                    "-> **被止损者大多一入场就错**, 属**择时/选股**问题, 非止损位置问题。 "
                    "次级: 40.1% 曾浮盈>0.5R 后被扫(真实但次要, SMC流动性扫荡视角)。 "
                    "持仓<2根K线者 **100% 止损**(n=120 全错); 持满12根者 avg+6.34%/PF8.64 "
                    "-> 退出机制本身在正确工作。**不得**据此放宽止损(共线性陷阱, 违反R7)"},
         {"id": "EXIT-CONVERGE", "name": "出场层裁定", "result": "非瓶颈, 改动收益有限",
          "detail": "盈亏比差的根源在**入场质量**, 非退出结构。兑现率 56-70% 并非严重低效; "
                    "未兑现率中位 0.42R。与R38早前\"退出参数现有结构局部最优\"一致, 本轮给出**机制解释**。 "
                    "**四层全部勘探完毕**: 筛选层(扩池/stage/rank) + 仓位层(加权/门槛) + "
                    "时序层(季节性) + 退出层(本轮) -> 仅 P1-7+P1-8 重基线为真实改进。 "
                    "剩余改进空间指向**入场择时质量**, 需新信息源(非现有特征集重组)"},
         {"id": "INDUSTRY-SOURCE", "name": "新信息源: 行业维度", "result": "唯一未接入源已启用",
          "detail": "hermes/data/industry_map.json (1.26MB, 5530项, 84行业) —— 长期挂为未决待办。 "
                    "结构: {updateDate, code, code_name, industry, industryClassification, symbol}。 "
                    "**匹配键必须是 symbol** (首版误用 code 得 0% 覆盖, 已修正); EVENT 覆盖 1527/1527 = 100%"},
         {"id": "INDUSTRY-CLUSTER", "name": "行业聚集效应(初测)", "result": "已否决(见INDUSTRY-REJECT)",
          "detail": "初测: trailing 聚集梯度 =0 +1.49%/PF1.77 -> >=8 +8.17%/PF21.23; "
                    "剔除 2024-02 后仍 +7.97%/PF9.58。IS/OOS: IS n=415 +7.06%/PF13.89 | OOS n=71 +9.49%/PF9.79。 "
                    "**但 date-shuffle 安慰剂后层内增量不显著(p=0.06)** -> 效应实为全市场增持潮代理, 已否决"},
         {"id": "INDUSTRY-REJECT", "name": "行业维度 date-shuffle 安慰剂", "result": "否决(结论反转)",
          "detail": "用**正确的 null**(打乱日期, 保持行业+收益+日期多重集)重做 200 次置换: "
                    "整体增量 +5.92pp vs null p95 +1.57 -> **p=0.0000(显著, 但那是全市场择时)**; "
                    "**层内增量(mkt固定) +3.12pp vs null p95 +3.17 -> p=0.0600 不显著**。 "
                    "-> 控制全市场增持潮后, 行业聚集**无法与随机日期区分** = 全市场择时代理。 "
                    "另: 逐年命中率 2023 0% / 2024 **40%** / 2025 4% / 2026 25% -> 几乎只在 2024 单一事件触发。 "
                    "与 C1(指数regime) 同型: 事后可见但控制混淆后无独立 edge。**关闭该方向**"},
         {"id": "PLACEBO-DISCIPLINE", "name": "置换 null 纪律(方法论)", "result": "新增通用规则",
          "detail": "**置换检验的 null 必须破坏被检验的那一维**: 检验\"行业特异\"时打乱**行业**标签是错的 "
                    "(日期结构残留, null 被高估: 打乱行业中位 +5.36pp vs 真实 +5.92pp); "
                    "必须打乱**日期**(或做层内配对)。 "
                    "**自我修正闭环**: R38ao 主动标注该缺陷并拒绝接线 -> 本轮验证标注正确; "
                    "若未标注会交付一个实为市场择时代理的伪信号"},
         {"id": "CONVERGE-REVISE", "name": "收敛结论修正(重要)", "result": "存在未勘探的新信息源",
          "detail": "此前结论\"四层勘探完毕、仅剩重基线\"需修正 —— 行业维度是**第 5 个维度且含真实增量**。 "
                    "它属\"新信息源\"(非现有特征集重组), 正是 R38an 指出的剩余空间所在。 "
                    "下一轮: ①date-shuffle 安慰剂重做 ②覆盖率漂移归因 ③若通过则全链路重放 + IS/OOS"},
         {"id": "GATE-AUDIT", "name": "rank 门槛反向审计(自审已交付改动)", "result": "通过, 但有保留",
          "detail": "把新沉淀的 R21/R22 反过来施加到自己已接线改动上。 ①逐年覆盖率 77.7~93.7% "
                    "**极差仅 1.2x**(对比行业维度 0%/40%/4%/25%) -> 非单一事件拟合; "
                    "②逐年增量 3/4 年为正(2024 +1.45 / 2025 +0.72 / 2026 +3.12pp); "
                    "③**层内增量混合**: 固定全市场增持强度后, [4,10] +1.02pp 与 [11,30] +1.74pp 明确, "
                    "但 [1,3] +0.07pp(~0)、[31,999] -4.66pp(n=15 不可靠); "
                    "④IS/OOS 覆盖率 91% vs 89% 极稳定。 -> **无需回滚**, 但不得夸大收益"},
         {"id": "GATE-HOT-LAYER", "name": "待复核: 高增持热度层", "result": "低 rank 票可能被误杀",
          "detail": "在全市场增持强度最高的层(同日候选>=31), rank<3 的 15 笔 avg 高达 **+12.00%** "
                    "(PF 294), 而 rank>=3 的 460 笔为 +7.34%。 虽 n=15 样本极小不可靠, 但提示: "
                    "**高热度期低 rank 票可能被门槛误杀**。 转下一轮课题: 待样本更大时复核, "
                    "若成立则考虑 mkt 自适应门槛(高热度期放宽)。"},
         {"id": "ENTRY-TIMING", "name": "入场择时维度(短动量)", "result": "否决",
          "detail": "检验入场前 1/3/5 日动量(此前未勘探维度)。 "
                    "快速止损率随 r5 上升单调下降(32%->1.2%)看似有效; "
                    "但 5日动量 **IS/OOS 方向完全相反**: IS 强势最优 +4.46%/PF4.81, "
                    "OOS 弱势反最优 +6.78%/PF7.26; 逐年矛盾(2024强/2026弱)。 "
                    "深度超跌(r20<-25%)x企稳交互 n=89 avg+10.96% 但 2024 占 82%(73笔), "
                    "2023/2025 零样本, OOS 仅 16 笔 -> 单事件拟合。 "
                    "-> 否决。 第6维度(筛选/仓位/时序/退出/行业/入场)全部勘探完毕"},
         {"id": "WIRE-E2E", "name": "生产接线端到端核查", "result": "代码在跑配置生效只差daily信号",
          "detail": "paper_ledger含rank_score字段(140条)代码在跑; 记录signal_date均早于今日09:24激活, rank_score=1/2的58条为历史回填非门槛失效; 门槛尚无真实新信号可过滤 -> 待办非缺陷"},
         {"id": "WIRE-E2E-FINAL", "name": "daily端到端验证(09-17)", "result": "门槛无事可做非失效",
          "detail": "09-17 00:00 daily选股完成: 38公告->16正事件->stage拒3->adx拒2->orders_created=0。 无任何信号通过stage+ADX走到rank评估阶段 -> 门槛(位于其后)无事可做 -> 无RANK_LT记录属正常, 与事件腿alpha窄带一致(扩池三连否已证)。 端到端最终状态: 代码在跑(paper_ledger含rank_score) + 配置生效(EVENT_RANK_GATE_MIN=3) + 门槛已就位"},
         {"id": "AUDIT-R39", "name": "外部审计修复(2026-09)", "result": "P0/P1已修复+回归锁",
          "detail": "外部审计关键发现经独立核实全部属实并修复: (1)编译阻断(run_v11_full截断+validate_skills 6处f-string)->compileall全绿; (2)V500未来函数TP->仅入场前可见结构(行为验证通过); (3)元组索引bug(c[3]->c[2])+排序(x[2]->x[3])。 回归锁tests_audit_v500_causality.py 9项全绿。 V11旧研究链不影响生产事件腿。 其余P0/P1(一次性全量检测/自适应参数look-ahead)属事件流架构重构, 记为后续"},
         {"id": "V699-REPLAY", "name": "V699 真实数据冻结回放(生产链重跑)", "result": "因果通过/经济失败(维持fail-closed)",
          "detail": "真实数据端到端: V697 18291种子(support_gate_pass) -> V698 oracle身份一致(18291==18291) -> "
                    "V699 冻结T+1严格回放 n=17469/WR52.65%/avg+1.24%/PF1.40。 "
                    "逐年: 2023 -1.05%(负) | 2024 +0.71% | 2025 +3.56% | 2026 -1.74%(负); "
                    "月度门槛失败(202304/05/06/07 n=1/2/1/4); promotion_gate_pass=false "
                    "-> 审计结论被真实数据再次确认: 保持 EMPTY_BOOK/fail-closed, 不做变体"},
         {"id": "V699-REGRESS", "name": "V699 Iter1c 回归发现与修复(重要)", "result": "回归已修复+回归锁6/6",
          "detail": "Iter1c(bf1a570) 用 pivot高<sweep_low 判定消费, 但合约要求 response收盘突破sweep高点 => "
                    "minimum_target>=response_high>sweep_high>sweep_low 恒成立 => 条件永假 => "
                    "visible_target 恒None => 18291种子 0 成交(NO_VISIBLE_UPSIDE_TARGET=18281)。 "
                    "旧属性测试用了违反源合约的合成几何(sweep低点>pivot高)故测试通过而生产全拒。 "
                    "正确语义: 摆动高点只在价格向上穿越(>=)时被消费; sweep低点穿透是SSL扫荡本身。 "
                    "修复后重跑: n=17469(与历史17600高度一致, 差异=消费检查排除272 vs 176 + 缓存刷新)。 "
                    "教训: 属性测试fixture必须满足源合约, 否则测试通过≠生产正确"},
         {"id": "V700-CONSIST", "name": "V700 扫描器四端一致 + 当前漏斗诊断(Iter6)", "result": "语义对齐+漏斗确认(维持fail-closed)",
          "detail": "v700 target 原实现只查 pivot>minimum, 未验证消费 —— 与修正后 V699 语义不一致 "
                    "(扫描器可能放行回放会拒的候选, 准入语义分裂)。已对齐(向上穿越>= = 消费) "
                    "+ 回归锁 tests_audit_v700_target.py 6/6。 "
                    "承诺epoch 20260814 当前漏斗: 4889→4888→108→20→20→2→2, full_current_setup=2, "
                    "buy_valid=0 = 第六层经济门槛正确生效(release_blocker=V699 promotion gate), "
                    "非信号设计过严 —— §8'选股量少'诊断: 结构层产出2个完整候选, "
                    "大幅下降层为 ssl_breach(4888→108) 与 sweep_reclaim(108→20)。维持 fail-closed"},
        {"id": "R38-CONVERGE", "name": "R38 迭代收敛(最终)", "result": "两处改进 + 一处口径修正",
         "detail": "18轮 12+ 假设测试完毕。真实改进: (1)ACCUM×2 温和加权(PF3.21→3.29) (2)Wilder+h12 合并重基线(PF3.08→3.72, MDD -629→-448) —— 后者性质是修正回测与生产的口径分叉。扩池三连否 + stage/rank/退出全部验证现状; 最高价值工作 = P1-7+P1-8 合并重基线(走审计)"},
    ],
    "production": [
        "生产 _market_proxy 弱市加仓机制正确保持(已验证 PF3.20→3.64) —— 唯一确认的生产机制",
        "技术腿: 未经稳健检验前不得接线(最优变体 OOS PF0.99 = 零 edge)",
        "业绩预增: 同口径 PF0.68 否决 —— 与基线 stage 过滤器(ACCUM/DOWNTREND)错配(利好出尽)",
        "stage 放宽: 否决 —— 现有白名单(ACCUM/DOWNTREND)经 OOS 验证为正确设计, 非保守惯性",
        "退出参数: 现有结构局部最优 —— 保持 CFG.MAX_HOLD=12(生产口径 OOS PF4.41/MDD-630 最优); 审计 P1-8 分叉已解决(非缺陷)",
         "已关闭: ACCUM x2 温和加权 -- 敞口归一通过但2024(最大样本n=149)劣化; 判别变量搜索(ACCUM & ret60<=-0.25)经敏感性扫描(跨度0.04)与置换检验(p=0.145)**否决** -> 事后选择阈值, 与季节性同型",
         "✅ 接线候选③已执行(2026-09-16, 用户批准): EVENT腿 rank_score>=3 —— config 开关 "
         "EVENT_RANK_GATE_MIN=3(env 可覆盖/=0 回滚), paper_sim 门槛已生效; 回归62库1299 PASS/0 FAIL "
         "预期 PF 3.35→3.52 / OOS 3.57→3.67 / MDD -415→-383; 待实盘/纸面观察确认",
        "首选候选: P1-7+P1-8 合并重基线 (Wilder ADX + max_hold=12) —— PF 3.08→3.72, MDD -629→-448, OOS PF 3.48→4.03, RR左尾 19.6→19.2%",
        "重基线性质 = 让回测追上生产(生产早已用Wilder, R38q 确认 L314-321/L744-745) —— 生产行为零变化, 审计风险 中→低",
         "⭐ 重基线已执行(2026-09-16, 用户批准): canonical combo_v20f_trades.csv 已接管",
         "  新基线(Wilder ADX + max_hold=12); EVENT n=1527 avg+3.767% PF3.63, OOS PF4.03; COMBO n=1861 avg+4.054% PF3.35 MDD-415",
         "  归档对照: archive/combo_v20f_trades_legacy_dx_h15.csv (n=1974 PF3.08 MDD-629); 生产行为零变化(让回测追上生产)",
        "扩池三连否: 技术腿(0.99) / 业绩预增(0.68) / stage放宽(1.09-1.88) —— '选股量少'是 alpha 内在属性, 不可通过扩量修复",
    ],
    "iterations": [
        {"round": "R38a", "commit": "351ebd8", "content": "三维复盘+多学派诊断+A1/B1证伪+C1初验"},
        {"round": "R38b", "commit": "017f964", "content": "C1敏感性+组合闸+候选池边界"},
        {"round": "R38c", "commit": "5535160", "content": "仓位缩放+2026特异性+技术腿可行性"},
        {"round": "R38d", "commit": "9f673a3", "content": "C1修正废弃(生产proxy正确)+量能闸验证+000157断言状态化"},
        {"round": "R38e", "commit": "7fbae53", "content": "两腿合并评估(信号x环境互补)"},
        {"round": "R38f", "commit": "09dab0f", "content": "前端同步(回测/选股/复盘面板 + /api/r38 实时轮询)"},
        {"round": "R38g", "commit": "4255d95", "content": "技术腿同口径回测(41%几何非法)+regime系数验证(适配成立)"},
        {"round": "R38h", "commit": "318f50f", "content": "技术腿独立SL/TP搜索(PF5.26)→IS/OOS检验 OOS PF0.99 否决"},
        {"round": "R38i", "commit": "b655dd6", "content": "事件腿扩池: 业绩预增晋级(裸持有)/业绩预减否决(退市偏差41.9%)"},
        {"round": "R38j", "commit": "7077c2f", "content": "业绩预增同口径回测: PF0.68 否决(与ACCUM/DOWNTREND过滤错配)"},
        {"round": "R38k", "commit": "6001498", "content": "stage白名单放宽: 否决(UPTREND PF1.09/MARKUP OOS0.96); 现有白名单验证正确"},
        {"round": "R38l", "commit": "d6813e2", "content": "ACCUM核心精选仓位: 温和正面(PF3.21→3.29); rank加权无效(路径关闭)"},
        {"round": "R38m", "commit": "9c42d9e", "content": "退出参数扫描(7配置): 现有退出局部最优; 审计P1-8分叉解决(生产12 OOS最优)"},
        {"round": "R38n", "commit": "4919b00", "content": "P1-7 ADX分叉量化: 旧版单窗DX双向出错; Wilder修复提升核心池(avg+1.06pp/PF+0.84)"},
        {"round": "R38o", "commit": "8f628da/36b4e71", "content": "P1-7注释方向复核 + 注释机制描述修正('偏低'改为'噪声大')"},
        {"round": "R38p", "commit": "e71a924/5930ae5", "content": "P1-7 Wilder重基线A/B: PF3.08→3.56/MDD-629→-490, 四项判据全过(晋级)"},
        {"round": "R38q", "commit": "640fd49", "content": "P1-7审计路径确认: 生产早已用Wilder → 重基线性质='回测追上生产', 风险中→低"},
        {"round": "R38r", "commit": "-", "content": "P1-7+P1-8合并重基线证据包: Wilder h12 = PF3.72/MDD-448/OOS4.03 最佳合并口径; 待批准执行审计"},
        {"round": "R38s", "commit": "-", "content": "P1-7+P1-8合并重基线执行完成(归档+新生成器+重认定+逐笔核对+全测试链); tests_regime断言按诚实原则更新"},
        {"round": "R38t", "commit": "61cdeba", "content": "重基线后 R38 结论复核: 4-5-6月弱势跨口径稳定; rank梯度再确认"},
        {"round": "R38u", "commit": "0f72bae", "content": "stage重扫(命中100%): ACCUM×2仍成立+0.14pp; 4/5/6月弱势归因(6月样本足最可信)"},
        {"round": "R38v", "commit": "6cd2f70", "content": "rank门槛IS/OOS: rank>=3/>=4 均过线; rank>=5否决(过严劣化) — 唯一通过稳健检验的信号层候选"},
        {"round": "R38w", "commit": "-", "content": "rank接线前置检查: 生产比回测多2项增持特征 → 语义不等价, 阻断天真接线"},
        {"round": "R38x", "commit": "0c1e934", "content": "生产口径rank重算: 分布位移-0.40(非上移); 最优门槛rank_prod>=3(OOS PF4.52), 回测>=4在生产失效"},
        {"round": "R38z", "commit": "ce121cf", "content": "rank全链路审计: 修正4.52→4.33; >=3与>=4 OOS相当但>=3多留41%量; >=4靠删CONT腿属隐藏耦合; 最终确认>=3(仅EVENT腿)"},
        {"round": "R38ab", "commit": "-", "content": "rank3研究分叉构建+验收: 与全链路审计逐项一致(n=1735/IS3.44/OOS3.67); 接线证据就绪"},
        {"round": "R38ac/ad", "commit": "d79fc67", "content": "rank>=3 生产接线执行: config开关(可回滚)+paper_sim门槛(仅EVENT腿)+26项回归锁; 回归62库全绿"},
        {"round": "R38af/ag", "commit": "ba059b9", "content": "门槛×月度(修正版): 未修好弱势月, 6月变差; 定性修正=门槛剔的是低于均值的赚钱票(质量换数量); 澄清 daily/loop 为两个独立入口"},
        {"round": "R38ah", "commit": "-", "content": "rank加权vs硬门槛: 假设证伪(加权=变相加杠杆, 累计优势纯来自敞口); 沉淀敞口归一方"},
        {"round": "R38ai", "commit": "-", "content": "季节性否决: 逐年验证3/3但多重检验p=0.788不显著; 修正4/5/6月恒亏说法; 沉淀逐年验证+多重检验两规则"},
        {"round": "R38aj", "commit": "-", "content": "研究纪律手册归档: 19条规则+失败案例+10步复用清单(handover/研究纪律手册.md)"},
        {"round": "R38ak", "commit": "-", "content": "ACCUM x2敞口归一复核: 形式通过(非纯杠杆)但仅近2年改善, 2024最大样本劣化 -> 降级观察项; 三情形定性表"},
        {"round": "R38al/am", "commit": "-", "content": "ACCUM x2 判别变量搜索: ret60<=-0.25看似可救2024, 但敏感性扫描(跨度0.04)与置换检验(p=0.145)否决 -> 研究线关闭; 沉淀阈值型规则纪律"},
        {"round": "R38an", "commit": "-", "content": "出场结构逐笔诊断: mae_r/mfe_r字段首次利用; SL_HIT mfe_r中位0.304 -> 止损非主因(属择时); 退出层非瓶颈, 四层勘探完毕"},
        {"round": "R38ao", "commit": "-", "content": "行业维度(唯一未接入新信息源): 聚集效应强(剔除2024-02后仍+7.97%), 2D分层有增量; 置换检验缺陷已自标 -> 强候选待确认, 不接线"},
        {"round": "R38aq/ar", "commit": "e58a6ea", "content": "纪律手册扩至23条(R20-R23: 置换null维/层内增量/覆盖率/自我修正); rank门槛反向审计通过(覆盖率1.2x, IS/OOS 91/89%)但层内增量混合"},
        {"round": "R38as", "commit": "-", "content": "入场择时维度否决(短动量IS/OOS方向相反 + 深度超跌交互2024占82%单事件); 第6维度勘探完毕"},
        {"round": "R39", "commit": "6aac8dc/8b61ac6", "content": "daily端到端验证最终结论(门槛无事可做非失效) + 外部审计P0/P1修复(编译阻断/V500未来函数/元组bug) + 回归锁9项"},
        {"round": "R38at/au", "commit": "47947ae/6a7fd0f", "content": "综合报告38轮收敛已出; 生产接线端到端核查通过(代码在跑配置生效), 门槛尚无真实新信号(daily待办)"},
        {"round": "R38ap", "commit": "-", "content": "行业维度date-shuffle安慰剂: 层内增量p=0.06不显著(实为全市场择时代理); 覆盖率极端不均(2024 40% vs 2025 4%) -> 否决; 沉淀置换null纪律"},
        {"round": "R40a", "commit": "-", "content": "V697/V698 真实数据重跑: 18291种子/oracle身份一致; V699首跑0成交 -> 发现Iter1c回归(恒False条件)"},
        {"round": "R40b", "commit": "-", "content": "V699 visible_target 回归修复(正确消费语义: 向上穿越=消费) + 回归锁重写6/6 + 重跑 n=17469 逐年逐月 -> 维持fail-closed; 前端新增v699_replay块"},
    ],
    "schools": {"ICT/SMC": 1250, "PriceAction": 229, "ChanLun缠论": 110, "Indicator": 214,
                "OrderFlow": 34, "Volume/VSA": 10, "Wyckoff": 5, "ElliottWave": 8, "TheStrat": 4},
}

data = {"updated": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "backtest": bt, "selection": sel, "merged": merged, "review": review}
if v699b: data["v699_replay"] = v699b
if v700b: data["v700_scanner"] = v700b
# audit_rebuild 块为手工同步内容(非本脚本生成), 重生成时必须保留, 不得丢失
try:
    prev = json.load(open(OUT, encoding="utf-8"))
    if isinstance(prev, dict) and "audit_rebuild" in prev:
        data["audit_rebuild"] = prev["audit_rebuild"]
except Exception:
    pass
json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"→ {OUT} ({os.path.getsize(OUT)} bytes)")
print(f"  事件腿 n={bt['base']['n']} PF={bt['base']['pf']} | 技术腿 n={sel['tech_v2']['n']} PF={sel['tech_v2']['pf']}")
print(f"  合并 n={merged['combined']['n']} avg={merged['combined']['avg']}%")

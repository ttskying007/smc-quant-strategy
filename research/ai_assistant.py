# -*- coding: utf-8 -*-
"""AI 实时交易分析助手（ai_assistant.py）—— MVP v1.0
独立轻量进程，作为"消费者 + 决策建议者 + 质疑者"，只读系统已产出的选股/回测/实时价，
对候选做 A/B/C 分级 + 仓位建议 + 盯盘预警 + 对话解释 + 策略质疑，并按自主度在
独立 ai_shadow 账本中经 core.execution.simulate 语义自动执行（带 MDD kill switch）。

设计铁律（与策略层同一纪律）：
  - 决策只用"入场时点可得"数据，绝不用未来 MFE/MAE/收盘价；
  - 不写回 paper_ledger/current_scanner_result 等策略源；
  - 输出全部落在 ai/ 目录（gitignore，可审计可回滚）；
  - 硬风控不可违反：单票<=25%、当日新开<=5、组合MDD<=10%则只平不开、
    数据不新鲜/未到valid_from/接近涨停不买、样本过小降级。

用法：
  python ai_assistant.py --day          # 读取系统当日候选并出 AI 决策画像
  python ai_assistant.py --monitor      # 盯盘循环（一次快照，可挂计划任务/循环）
  python ai_assistant.py --auto         # 受控自动：对 A 级候选用 core 语义进 ai_shadow
  python ai_assistant.py --chat "..."   # 对话/质疑（规则模板引擎）
  python ai_assistant.py --test         # 运行内建单元测试
"""
import io, json, os, re, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as CFG
import core.execution as EX

AI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai")
RESEARCH = CFG.RESEARCH_DIR
LEDGER = os.path.join(RESEARCH, "paper_ledger.json")
BACKTEST = os.path.join(RESEARCH, "handover", "最新回测数据", "逐笔交易全明细.json")
LIVE_KEYS = CFG.KT_CACHE  # 用于确认数据日期/代码存在
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      "Referer": "https://finance.sina.com.cn/"}

# ---------------- 默认配置（可调整） ----------------
DEFAULTS = {
    "initial_capital": 100000.0,
    "risk_per_trade_pct": 0.01,
    "max_position_pct": 0.25,
    "max_open_positions": 5,
    "max_daily_new": 5,
    "portfolio_mdd_kill": 0.10,
    "ai_autonomy": "auto",          # advise | approve | auto
    "min_sample": 30,               # 信号历史最小样本，低于则降级 B
    "gap_chase_atr": 0.5,           # 现价距入场参考超过该 ATR 倍数 => 追高惩罚
    "funnel_alarm_sigma": 2.0,      # 漏斗异常 z 阈值
    "monitor_interval_sec": 45,     # 盯盘轮询间隔
}
# 打分权重（可逐周调）
SCORE_WEIGHTS = {
    "avgnet_z": 2.0, "wr_z": 1.5, "pf_z": 1.2,
    "sample": 0.6, "freshness": 1.0, "market": 1.0,
    "gap_penalty": 1.5, "oos_weak": 2.0,
}


def load_config():
    cfg = dict(DEFAULTS)
    p = os.path.join(AI_DIR, "ai_config.json")
    if os.path.exists(p):
        try:
            cfg.update(json.load(open(p, encoding="utf-8")))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    os.makedirs(AI_DIR, exist_ok=True)
    with open(os.path.join(AI_DIR, "ai_config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _w(name):
    return SCORE_WEIGHTS.get(name, 1.0)


# ---------------- 数据接入 DataIngest ----------------
def _load_json(path, default=None):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _code6(symbol):
    return str(symbol or "").split(".")[0]


def load_ledger():
    led = _load_json(LEDGER, [])
    if not isinstance(led, list):
        led = []
    return led


def load_backtest():
    d = _load_json(BACKTEST, {})
    if isinstance(d, dict):
        return d.get("trades") or []
    return d or []


def load_live_prices(codes):
    """Sina 实时价：返回 {code: {px,prev,open,vol}}。失败跳过。"""
    if not codes:
        return {}
    syms = [("sh" if c.startswith("6") else "sz") + c for c in codes]
    out = {}
    for i in range(0, len(syms), 50):
        batch = syms[i:i + 50]
        url = "https://hq.sinajs.cn/list=" + ",".join(batch)
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                b = r.read().decode("gbk", errors="replace")
            for line in b.strip().split("\n"):
                if "hq_str_" not in line:
                    continue
                parts = line.split('="', 1)
                sym = parts[0].split("_")[-1]
                vals = parts[1].rstrip('";').split(",")
                if len(vals) > 5 and vals[3]:
                    try:
                        px = float(vals[3])
                        if px > 0:
                            out[sym[2:]] = {"px": px,
                                            "prev": float(vals[2]) if len(vals) > 2 and vals[2] else 0.0,
                                            "open": float(vals[1]) if len(vals) > 1 and vals[1] else 0.0,
                                            "vol": float(vals[8]) if len(vals) > 8 and vals[8] else 0.0}
                    except Exception:
                        pass
        except Exception:
            pass
    return out


def latest_kline_date(code):
    """返回该 code 最近K线日期（YYYYMMDD）。无数据返回空串。"""
    ex = "SH" if code.startswith("6") else "SZ"
    p = os.path.join(LIVE_KEYS, f"{code}_{ex}_daily_800.json")
    raw = _load_json(p, [])
    if not raw:
        return ""
    last = raw[-1]
    return "".join(c for c in str(last.get("t") or "") if c.isdigit())[:8]


def market_latest_date():
    """从全市场文件推断最新数据日（用最多文件的日期）。"""
    try:
        files = [f for f in os.listdir(LIVE_KEYS) if f.endswith("_daily_800.json")]
    except Exception:
        return ""
    from collections import Counter
    cnt = Counter()
    for f in files[:2000]:  # 采样以省时
        raw = _load_json(os.path.join(LIVE_KEYS, f), [])
        if raw:
            t = "".join(c for c in str(raw[-1].get("t") or "") if c.isdigit())[:8]
            if t:
                cnt[t] += 1
    return cnt.most_common(1)[0][0] if cnt else ""


def _z(vals, v):
    """z-score（样本>=3）；样本过小返回0。"""
    if not vals or len(vals) < 3:
        return 0.0
    m = sum(vals) / len(vals)
    sd = (sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5 or 1e-9
    return (v - m) / sd


# ---------------- 历史回测统计（按 signal 信号/leg 分层） ----------------
def build_signal_stats(bt_trades):
    """统计每个信号键的历史表现（仅用历史已平仓单，OOS/IS 分段）。
    key = f"{leg}|{signal_chain 前两段}"。返回 {key: {n,avg_net,wr,pf,ooc_avg_net,...}}"""
    stats = {}
    for t in bt_trades:
        leg = str(t.get("leg") or "")
        chain = str(t.get("signal_chain") or "")
        key = f"{leg}|{chain}"
        d = stats.setdefault(key, {"net": [], "won": 0, "n": 0, "entry": []})
        np_ = float(t.get("net_pnl_pct") or 0)
        d["net"].append(np_)
        d["n"] += 1
        if np_ > 0:
            d["won"] += 1
        d["entry"].append(str(t.get("entry_date") or ""))
    out = {}
    for k, d in stats.items():
        n = d["n"]
        avg = sum(d["net"]) / n
        wr = d["won"] / n
        wins = [x for x in d["net"] if x > 0]
        losses = [x for x in d["net"] if x <= 0]
        pf = (sum(wins) / abs(sum(losses))) if sum(losses) != 0 else float("inf")
        # 时间 OOS 分段：2025 中后为 OOS（与本项目 OOS 口径一致）
        oos = [x for x, e in zip(d["net"], d["entry"]) if e and e >= "20250701"]
        oos_avg = (sum(oos) / len(oos)) if oos else None
        out[k] = {"n": n, "avg_net": round(avg, 3), "wr": round(wr, 3),
                  "pf": (round(pf, 2) if pf != float("inf") else None),
                  "oos_avg": (round(oos_avg, 3) if oos_avg is not None else None),
                  "oos_n": len(oos)}
    return out


def signal_key_of(order, leg):
    """为候选构造与回测一致的信号键。
    回测 EVENT 腿统一用链 'insider-event'（n=3552, avg 7.07%, PF 7.9, OOS 6.28%）。
    因此 EVENT 候选映射到 'EVENT|insider-event' 以命中腿级历史统计；
    SMC/CONT 无稳定回测键，按 leg 兜底（SMC 生产禁用，实际走不到）。"""
    if leg == "EVENT":
        return "EVENT|insider-event"
    if leg == "SMC":
        return "SMC"
    return f"{leg}|" + str(order.get("signal_combo") or "")


# ---------------- 决策核心 JudgeEngine ----------------
def judge_candidate(order, live, bt_stats, cfg, mkt_date):
    """对单个候选做 A/B/C 分级 + 仓位 + 理由 + 质疑。返回 dict。"""
    code = _code6(order.get("code"))
    leg = str(order.get("source") or order.get("signal_combo") or "EVENT")
    # 归一 leg 标签
    if order.get("source") == "EVENT" or "EVENT" in leg:
        leg_l = "EVENT"
    elif order.get("source") == "SMC" or "SMC" in leg:
        leg_l = "SMC"
    elif order.get("source") == "CONT" or "CONT" in leg:
        leg_l = "CONT"
    else:
        leg_l = "EVENT"
    entry_ref = float(order.get("entry_price") or 0)
    sl = float(order.get("sl1") or order.get("sl_price") or 0)
    tp = float(order.get("tp2") or order.get("tp_price") or 0)
    px = None
    if code in live:
        px = live[code].get("px")
    reason_notes = []
    challenges = []
    status = order.get("status") or ""

    # 硬风控（block 即不入 A/B，进 C）
    hard_block = []
    # 1. 数据新鲜度
    kdate = latest_kline_date(code)
    if mkt_date and kdate and kdate < mkt_date:
        hard_block.append(f"数据过期(K线{kdate}<市场{mkt_date})")
    # 2. 未到可成交日（valid_from > 今日）
    vf = str(order.get("valid_from") or "")
    today = time.strftime("%Y%m%d")
    if vf and vf > today:
        status = "PENDING_NEXT_OPEN"
        reason_notes.append(f"待 {vf} 开盘")
    # 3. 接近涨停不追（现价距昨收超过板块幅度-0.5%）
    if px and live[code].get("prev"):
        pct = px / live[code]["prev"] - 1
        lmt = EX.limit_pct_for(code)
        if pct >= lmt - 0.005:
            hard_block.append(f"现价涨停+{pct*100:.1f}%不可追")
    # 4. 样本过小 => 降级（不算硬block，但进质疑）
    sk = signal_key_of(order, leg_l)
    st = bt_stats.get(sk)
    if st is None:
        # 用更宽松键（只按 leg）兜底
        sk = leg_l
        st = bt_stats.get(sk)
    if st is None or st["n"] < cfg["min_sample"]:
        challenges.append(f"信号样本不足(n={st['n'] if st else 0}<{cfg['min_sample']})，历史不可靠，降级观察")
        small_sample = True
    else:
        small_sample = False

    # 分析师打分
    score = 0.0
    if st and st["n"] >= 3:
        score += _w("avgnet_z") * _z(st["net"], st["avg_net"]) if False else _w("avgnet_z") * max(-1.0, min(1.0, st["avg_net"] / 5.0))
        score += _w("wr_z") * (st["wr"] - 0.5) * 2
        score += _w("pf_z") * (min((st["pf"] or 1.0), 3.0) - 1.0) / 2.0
        score += _w("sample") * min(1.0, st["n"] / 200.0)
        if st["oos_n"] >= 10 and st["oos_avg"] is not None and st["oos_avg"] < 0:
            score -= _w("oos_weak")
            challenges.append(f"时间OOS均值{st['oos_avg']}%为负，历史 edge 未外推")
        # 解释
        if st["n"]:
            reason_notes.append(f"历史n={st['n']} avg={st['avg_net']}% wr={st['wr']*100:.0f}% pf={st['pf'] if st['pf'] is not None else '∞'} oos={st['oos_avg']}%")
    score += _w("freshness") * (0.5 if not hard_block else -1.0)
    # 追高惩罚：现价距 entry_ref gap
    if px and entry_ref > 0:
        gap = px / entry_ref - 1
        if gap > cfg["gap_chase_atr"]:
            score -= _w("gap_penalty")
            challenges.append(f"现价{px:.2f}高于入场参考{entry_ref:.2f} {gap*100:.1f}%，追高风险")

    # 操盘手：仓位（风险平价）
    position_pct = 0.0
    risk_dist = (entry_ref - sl) if (entry_ref and sl and entry_ref > sl) else None
    if risk_dist and entry_ref > 0:
        pos = cfg["risk_per_trade_pct"] / (risk_dist / entry_ref)
        position_pct = round(min(pos, cfg["max_position_pct"]), 4)
        # FIX(2026-09-08, regime 发现正向应用): 弱市加权与 paper_sim 一致 ——
        # 事件腿逆向策略, 弱市信号质量最高; w = clip(1 - k×proxy, 0.3, 2.0)。
        try:
            from paper_sim import _market_proxy as _mp
            _pr = _mp(code)
            if CFG.WEAK_MARKET_WEIGHT and _pr is not None:
                _reg_w = max(CFG.WEAK_MARKET_W_MIN, min(CFG.WEAK_MARKET_W_MAX,
                                                        1.0 - CFG.WEAK_MARKET_K * _pr))
                position_pct = round(min(position_pct * _reg_w, cfg["max_position_pct"]), 4)
        except Exception:
            pass  # 权重不可得时保持风险平价原仓位
    else:
        challenges.append("风险距离不可算(entry<=sl)，无法定仓")

    # 风控：组合/当日上限（调用方在 auto 中执行聚合约束）

    # 分级
    if hard_block:
        grade = "C"
        action = "不碰"
        reason_notes = hard_block + reason_notes
    elif score >= 1.2 and not small_sample and position_pct > 0:
        grade = "A"
        action = "可买"
    elif score >= 0.3 or (small_sample and score >= 0.5):
        grade = "B"
        action = "观察"
    else:
        grade = "C"
        action = "不碰"

    return {
        "code": code, "name": order.get("name") or code, "leg": leg_l,
        "status": status, "signal_combo": order.get("signal_combo"),
        "signal_date": order.get("signal_date"), "valid_from": order.get("valid_from"),
        "entry_ref": entry_ref, "sl": sl, "tp": tp,
        "live_px": px, "signal_key": sk,
        "hist": st, "score": round(score, 2), "grade": grade, "action": action,
        "position_pct": position_pct, "risk_dist_pct": (round(risk_dist/entry_ref*100,2) if risk_dist and entry_ref else None),
        "reasons": reason_notes, "challenges": challenges, "blocked": bool(hard_block),
    }


def judge_all(cfg):
    """对系统所有候选（PENDING/FILLED/CLOSED 中未决）产出 AI 画像。返回 dict。"""
    led = load_ledger()
    bt = load_backtest()
    bt_stats = build_signal_stats(bt)
    # 只对"可参与/在持仓"的候选做决策：PENDING 与 FILLED
    cands = [t for t in led if t.get("status") in ("PENDING_ORDER", "FILLED")]
    codes = {_code6(t.get("code")) for t in cands}
    live = load_live_prices(list(codes))
    mkt = market_latest_date()
    result = [judge_candidate(t, live, bt_stats, cfg, mkt) for t in cands]
    # 按 grade 排序 A > B > C
    order_g = {"A": 0, "B": 1, "C": 2}
    result.sort(key=lambda r: (order_g.get(r["grade"], 3), -r["score"]))
    return {"asof": time.strftime("%Y-%m-%d %H:%M:%S"), "market_date": mkt,
            "candidates": result, "live_count": len(live)}


# ---------------- 盯盘 Monitor ----------------
def monitor_snapshot(decisions):
    """对候选/持仓做盯盘快照，产出预警。返回 {code: [alerts], ...}。"""
    alerts = {}
    codes = [d["code"] for d in decisions if d["live_px"] is not None] or [d["code"] for d in decisions]
    live = load_live_prices(codes)
    for d in decisions:
        code = d["code"]
        px = live.get(code, {}).get("px") if code in live else d["live_px"]
        if not px:
            continue
        sl, tp, ep = d.get("sl") or 0, d.get("tp") or 0, d.get("entry_ref") or 0
        lst = []
        if sl and px <= sl:
            lst.append("破SL(结构失效)")
        elif sl and px <= sl * 1.005:
            lst.append("逼近SL(5‰内)")
        if tp and px >= tp:
            lst.append("达TP(考虑止盈)")
        elif tp and px >= tp * 0.985:
            lst.append("逼近TP")
        if ep and px / ep - 1 <= -0.08:
            lst.append("入场后浮亏超8%")
        if live[code].get("vol") == 0:
            lst.append("停牌/无量")
        if live[code].get("prev"):
            pct = px / live[code]["prev"] - 1
            lmt = EX.limit_pct_for(code)
            if pct >= lmt - 0.005:
                lst.append(f"涨停封死")
            if pct <= -(lmt - 0.005):
                lst.append(f"跌停")
        if lst:
            alerts[code] = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "name": d["name"],
                            "px": px, "alerts": lst}
    return alerts


# ---------------- 对话/质疑 ChatSession（规则模板 + LLM 挂钩） ----------------
def chat_answer(question, decisions):
    """规则模板对话引擎。question 匹配意图返回解释；否则返回可复述的画像摘要。"""
    q = str(question or "").strip()
    ql = q.lower()
    answer_lines = []
    # 今日可买
    if "买" in q or "可以买" in q or "可买" in q or "建议" in q or "推荐" in q:
        a = [d for d in decisions if d["grade"] == "A"]
        b = [d for d in decisions if d["grade"] == "B"]
        if a:
            answer_lines.append("今日 A 级可买（高置信）：")
            for d in a[:5]:
                answer_lines.append(f"  {d['code']} {d['name']} score={d['score']} 仓{d['position_pct']*100:.1f}% SL={d['sl']} TP={d['tp']}")
                for r in d["reasons"][:2]:
                    answer_lines.append(f"     · {r}")
        else:
            answer_lines.append("今日无 A 级可买候选。")
        if b:
            answer_lines.append("B 级观察（等确认）：")
            answer_lines.append("  " + "、".join(f"{d['code']}" for d in b[:8]))
    # 某只股票
    for d in decisions:
        if d["code"] in q or (d["name"] and d["name"] in q):
            answer_lines.append(f"[{d['code']} {d['name']}] 组合={d['signal_combo']} 触发={d['signal_date']} 状态={d['status']}")
            answer_lines.append(f"  入场参考={d['entry_ref']} SL={d['sl']} TP={d['tp']} 现价={d['live_px']}")
            answer_lines.append(f"  AI分级={d['grade']} score={d['score']} 建议仓位={d['position_pct']*100:.1f}%")
            for r in d["reasons"]:
                answer_lines.append("  · " + r)
            for c in d["challenges"]:
                answer_lines.append("  ⚠ " + c)
    # 质疑/风险
    if "质疑" in q or "风险" in q or "为什么" in q or "凭" in q or "批评" in q or "质疑" in q:
        for d in decisions:
            if d["challenges"]:
                answer_lines.append(f"[{d['code']}] 质疑：")
                for c in d["challenges"]:
                    answer_lines.append("  · " + c)
    # 信号链解释
    if "信号" in q or "组合" in q or "链" in q or "触发" in q:
        for d in decisions:
            answer_lines.append(f"[{d['code']}] 信号链：{d['signal_key']}")
            if d["hist"]:
                h = d["hist"]
                answer_lines.append(f"  历史: n={h['n']} avg={h['avg_net']}% wr={h['wr']*100:.0f}% pf={h['pf']} oos={h['oos_avg']}%")
    if not answer_lines:
        answer_lines.append("可问我：今天买什么 / 某只股票怎么样 / 质疑哪些信号 / 解释某信号链。")
    return "\n".join(answer_lines)


# ---------------- 策略质疑 Feedback（漏斗异常） ----------------
def strategy_feedback(decisions, cfg):
    """基于 AI 决策漏斗 + 系统 selection_result，产出给策略层的质疑。返回 dict。"""
    fb = {"asof": time.strftime("%Y-%m-%d %H:%M:%S"), "funnel": {}, "challenges": []}
    sel = _load_json(os.path.join(RESEARCH, "selection_result.json"), {})
    fb["funnel"] = {
        "selected": sel.get("stats", {}).get("selected"),
        "skipped_stage": sel.get("stats", {}).get("skipped_stage"),
        "skipped_adx": sel.get("stats", {}).get("skipped_adx"),
        "skipped_nodata": sel.get("stats", {}).get("skipped_nodata"),
        "skipped_noise": sel.get("stats", {}).get("skipped_noise"),
    }
    # AI 质疑汇总（给策略层）
    agg = {}
    for d in decisions:
        for c in d["challenges"]:
            agg[c] = agg.get(c, 0) + 1
    top = sorted(agg.items(), key=lambda kv: -kv[1])[:8]
    for msg, cnt in top:
        fb["challenges"].append({"count": cnt, "suggestion": msg})
    return fb


# ---------------- 受控自动执行（ai_shadow） ----------------
AI_SHADOW = os.path.join(AI_DIR, "ai_shadow_ledger.json")
AI_EQ = os.path.join(AI_DIR, "ai_equity.json")

def load_ai_shadow():
    return _load_json(AI_SHADOW, [])


def save_ai_shadow(rows):
    os.makedirs(AI_DIR, exist_ok=True)
    with open(AI_SHADOW, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def _net_eq(shadow, initial):
    eq = initial
    for r in shadow:
        if r.get("status") == "CLOSED" and r.get("pnl_pct") is not None:
            eq *= (1 + r.get("pnl_pct") / 100.0 * r.get("position_pct", 0.0))
    return eq


def _max_dd(shadow, initial):
    eq = initial
    peak = initial
    mdd = 0.0
    for r in sorted(shadow, key=lambda x: str(x.get("filled_at") or "")):
        if r.get("status") == "CLOSED" and r.get("pnl_pct") is not None:
            eq *= (1 + r.get("pnl_pct") / 100.0 * r.get("position_pct", 0.0))
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > mdd:
                mdd = dd
    return mdd


def auto_execute(decisions, cfg, dry_run=True):
    """受控自动：对 A 级候选经 core.execution.simulate 语义进 ai_shadow。
    聚合约束：当日新开<=max_daily_new、组合MDD<=kill、单票<=max_position。
    dry_run=True 时只模拟不落盘（用于演练/测试）。"""
    shadow = load_ai_shadow() if not dry_run else []
    initial = cfg["initial_capital"]
    # 当日已开
    today = time.strftime("%Y-%m-%d")
    opened_today = sum(1 for r in shadow if str(r.get("filled_at") or "")[:10] == today)
    # 组合回撤
    mdd = _max_dd(shadow, initial) if shadow else 0.0
    if mdd >= cfg["portfolio_mdd_kill"]:
        return {"action": "kill", "reason": f"组合MDD {mdd*100:.1f}% 触发kill", "trades": []}
    results = []
    opened = opened_today
    for d in decisions:
        if d["grade"] != "A":
            continue
        if opened >= cfg["max_daily_new"]:
            results.append({"code": d["code"], "skip": "当日新开达上限"})
            continue
        # 现价需在 SL 与 TP 之间且非涨停（可成交）
        if not d["live_px"]:
            results.append({"code": d["code"], "skip": "无实时价"})
            continue
        if d["blocked"]:
            results.append({"code": d["code"], "skip": "硬风控拦截"})
            continue
        # 用 core.execution 语义模拟持有（从下一交易日起，最多 MAX_HOLD 根）
        bs = _load_json(os.path.join(LIVE_KEYS, _kpath(d["code"])), [])
        daily = []
        for x in bs:
            t = "".join(c for c in str(x.get("t") or "") if c.isdigit())[:8]
            if t and x.get("o") and x.get("h") and x.get("l") and x.get("c"):
                daily.append({"t": t, "o": float(x["o"]), "h": float(x["h"]), "l": float(x["l"]), "c": float(x["c"]), "v": float(x.get("v") or 0)})
        daily.sort(key=lambda b: b["t"])
        # 找入场日：signal 之后第一个有K线的交易日
        sig = str(d.get("signal_date") or "").replace("-", "")
        dates = [b["t"] for b in daily]
        ei = -1
        for i, dt in enumerate(dates):
            if dt > sig:
                ei = i
                break
        if ei < 0 or ei >= len(daily):
            results.append({"code": d["code"], "skip": "signal后无入场K线"})
            continue
        ep = daily[ei]["o"]
        sl, tp = d["sl"], d["tp"]
        if not (ep > 0 and sl > 0 and tp > 0 and ep > sl):
            results.append({"code": d["code"], "skip": "入场/SL/TP不合法"})
            continue
        pos = min(d["position_pct"], cfg["max_position_pct"])
        r = EX.simulate(daily, ei, ep, sl, tp2=tp, max_hold=CFG.MAX_HOLD,
                        code=d["code"])
        pnl = r.get("net_pnl_pct", 0.0)
        rec = {
            "code": d["code"], "name": d["name"], "leg": d["leg"], "grade": "A",
            "signal_date": d["signal_date"], "filled_at": dates[ei], "buy_price": round(ep, 3),
            "sell_price": round(r["exit_price"], 3), "exit_reason": r["reason"],
            "position_pct": pos, "pnl_pct": round(pnl, 3), "hold_bars": r["hold_bars"],
            "mfe_r": round(r.get("mfe_r", 0), 2), "mae_r": round(r.get("mae_r", 0), 2),
        }
        results.append(rec)
        if not dry_run and not r.get("skipped"):
            shadow.append(rec)
            opened += 1
    eq = _net_eq(shadow, initial) if shadow else initial
    if not dry_run:
        save_ai_shadow(shadow)
        with open(AI_EQ, "w", encoding="utf-8") as f:
            json.dump({"asof": time.strftime("%Y-%m-%d %H:%M:%S"), "equity": round(eq, 2),
                       "max_drawdown": round(_max_dd(shadow, initial), 4), "closed": len([x for x in shadow if x.get("status")=="CLOSED"])}, f, ensure_ascii=False, indent=2)
    return {"action": "executed", "equity_after": round(eq, 2), "trades": results}


def _kpath(code):
    ex = "SH" if code.startswith("6") else "SZ"
    return f"{code}_{ex}_daily_800.json"


# ---------------- 输出画像 & CLI ----------------
def dump_decision_json(decisions):
    os.makedirs(AI_DIR, exist_ok=True)
    with open(os.path.join(AI_DIR, "ai_decision.json"), "w", encoding="utf-8") as f:
        json.dump(decisions, f, ensure_ascii=False, indent=2)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", action="store_true", help="当日 AI 决策画像")
    ap.add_argument("--monitor", action="store_true", help="盯盘快照")
    ap.add_argument("--auto", action="store_true", help="受控自动执行(ai_shadow)")
    ap.add_argument("--dry-run", action="store_true", help="auto 演练不落盘")
    ap.add_argument("--chat", type=str, help="对话/质疑")
    ap.add_argument("--feedback", action="store_true", help="策略质疑输出")
    ap.add_argument("--test", action="store_true", help="运行内建测试")
    args = ap.parse_args()
    cfg = load_config()

    if args.test:
        sys.exit(run_tests())

    if args.day or args.monitor or args.auto or args.feedback or args.chat is not None:
        dec = judge_all(cfg)
        dump_decision_json(dec)
        if args.day:
            print(f"AI 决策 asof={dec['asof']} 市场={dec['market_date']} 候选={len(dec['candidates'])}")
            for d in dec["candidates"]:
                print(f"  [{d['grade']}] {d['code']} {d['name']} score={d['score']} 仓={d['position_pct']*100:.1f}% SL={d['sl']} TP={d['tp']} 现价={d['live_px']}")
                for r in d["reasons"][:2]:
                    print(f"      · {r}")
        if args.monitor:
            al = monitor_snapshot(dec["candidates"])
            print(f"盯盘: {len(al)} 条异常")
            for code, a in al.items():
                print(f"  {code} {a['name']} px={a['px']}: {','.join(a['alerts'])}")
        if args.feedback:
            fb = strategy_feedback(dec["candidates"], cfg)
            print(f"策略质疑: 漏斗={fb['funnel']}")
            for c in fb["challenges"]:
                print(f"  ×{c['count']} {c['suggestion']}")
        if args.auto:
            res = auto_execute(dec["candidates"], cfg, dry_run=args.dry_run)
            print(f"AI 自动执行: {res['action']} 净值后={res.get('equity_after')}")
            for t in res.get("trades", [])[:10]:
                if "skip" in t:
                    print(f"  {t['code']} skip={t['skip']}")
                else:
                    print(f"  {t['code']} buy={t['buy_price']} sell={t['sell_price']} reason={t['exit_reason']} pnl={t['pnl_pct']}%")
        if args.chat is not None:
            print(chat_answer(args.chat, dec["candidates"]))
        return
    print(__doc__)


# ---------------- 内建测试 ----------------
def run_tests():
    ok = lambda n, c, d="": print(("  OK " if c else "  FAIL ") + n + ((" " + str(d)) if d else ""))
    P = [0, 0]
    def chk(name, cond, detail=""):
        P[1 if not cond else 0] += 1
        ok(name, cond, detail)

    # 1. 信号统计 & 时间 OOS 分段
    bt = [{"leg": "EVENT", "signal_chain": "sweep:2026|OB:2026", "net_pnl_pct": 5.0, "entry_date": "20250101"},
          {"leg": "EVENT", "signal_chain": "sweep:2026|OB:2026", "net_pnl_pct": -3.0, "entry_date": "20240101"},
          {"leg": "EVENT", "signal_chain": "sweep:2026|OB:2026", "net_pnl_pct": 2.0, "entry_date": "20250801"}]
    stats = build_signal_stats(bt)
    k = "EVENT|sweep:2026|OB:2026"
    chk("信号统计聚合", k in stats and stats[k]["n"] == 3, stats.keys())
    chk("OOS 分段(>=20250701)", stats[k]["oos_n"] == 1 and abs(stats[k]["oos_avg"] - 2.0) < 1e-6, stats[k])

    # 2. judge_candidate 硬风控：涨停不买
    cfg = load_config()
    live = {"000001": {"px": 11.0, "prev": 10.0, "open": 10.5, "vol": 1000}}
    order = {"code": "000001", "entry_price": 10.5, "sl1": 9.5, "tp2": 11.5,
             "source": "EVENT", "signal_combo": "BUYBACK", "signal_date": "20260904",
             "valid_from": "20260907", "status": "PENDING_ORDER", "sub_signals": "sweep:2026|OB:2026"}
    r = judge_candidate(order, live, stats, cfg, "20260904")
    chk("涨停硬风控→C", r["grade"] == "C" and r["blocked"], r["grade"])

    # 3. 追高惩罚（用健康样本，让追高成为主要制约）
    live3 = {"000001": {"px": 10.9, "prev": 10.0, "open": 10.5, "vol": 1000}}  # +9% 主板可买
    good_stats = {"EVENT|sweep:2026|OB:2026": {"n": 120, "avg_net": 6, "wr": 0.65, "pf": 2.5, "oos_avg": 5, "oos_n": 60}}
    r3 = judge_candidate(dict(order, valid_from="20260904", entry_price=6.0, sl1=5.5), live3, good_stats, cfg, "20260904")
    chk("追高惩罚进质疑", any("追高" in c for c in r3["challenges"]), r3["challenges"])

    # 4. 样本不足降级
    r4 = judge_candidate(order, live3, {"EVENT|sweep:2026|OB:2026": {"n": 5, "avg_net": 5, "wr": 0.6, "pf": 2, "oos_avg": 5, "oos_n": 5}}, cfg, "20260904")
    chk("样本<min→质疑", any("样本" in c for c in r4["challenges"]), r4["challenges"])

    # 5. 仓位风险平价（关闭弱市加权验证纯公式；加权单独验证）
    _saved_wm = CFG.WEAK_MARKET_WEIGHT
    CFG.WEAK_MARKET_WEIGHT = False
    r4b = judge_candidate(order, live3, {"EVENT|sweep:2026|OB:2026": {"n": 5, "avg_net": 5, "wr": 0.6, "pf": 2, "oos_avg": 5, "oos_n": 5}}, cfg, "20260904")
    CFG.WEAK_MARKET_WEIGHT = _saved_wm
    chk("仓位=预算/风险距离", abs(r4b["position_pct"] - 0.01/(1.0/10.5)) < 0.002, r4b["position_pct"])

    # 6. auto_execute dry_run 不落盘、有 kill 检查
    res = auto_execute([], cfg, dry_run=True)
    chk("auto dry-run 安全", res["action"] in ("executed", "kill"), res)

    # 7. chat 引擎
    ans = chat_answer("今天买什么", [{"code": "000001", "name": "X", "grade": "A", "score": 1.5,
                                      "position_pct": 0.2, "sl": 9, "tp": 11, "entry_ref": 10, "live_px": 10.3,
                                      "reasons": ["历史强"], "challenges": [], "signal_combo": "B", "signal_date": "20260904",
                                      "status": "PENDING", "signal_key": "EVENT|s", "hist": None}])
    chk("chat 可买回答", "可买" in ans, ans[:40])

    print(f"\n结果: PASS={P[0]} FAIL={P[1]}")
    return 1 if P[1] else 0


if __name__ == "__main__":
    main()
# -*- coding: utf-8 -*-
"""生成 v21 结构增强回测 CSV —— research/handover/nextgen_v21_spec.md 的实现。

本文件 = gen_v20f2_wilder_h12.py 的逐行复制 + **仅加列**(引擎/过滤链/阈值零改动):
  R33 缺口: sub_signals / rank_components / stage_span / adx_span
  E4''+:   trend_state / last_event_*(BOS/CHoCH) / broken_low_level / sl_below_structure
           / supply_layers / nearest_supply_dist / zone_90d / board
全部新列 = 信号日因果口径(结构事件只计确认bar<=信号日, 无前视)。
结构事件单源: core.structure.structure_events (R57 新增, r53b 检测器收敛)。

**不写 canonical**: 输出 combo_v21_trades.csv; v20f 冻结基线与 139 消费者零接触。
执行需用户批准(全市场 15-30 分钟)。验收标准见 spec §验收。
---
以下为 v20f2 原始头注(引擎口径沿革留档):

本文件 = gen_v20f.py 的逐行复制 + **仅两处口径修正**，用于消除回测与生产的
两个已知分叉（第八轮审计 P1-7 / P1-8）：

  ① ADX: legacy 单窗 DX(|PDI-MDI|/(PDI+MDI)) → core.indicators.adx14_of
     （标准 Wilder 平滑 ADX(14)，生产 paper_sim EVENT 腿在用，2026-09-12 修复）
  ② max_hold: 15 → CFG.MAX_HOLD(12)，与生产统一退出持有期

性质（审计 P1-7/P1-8 结论）: 本重基线 = **"让回测追上生产"** —— 生产
paper_sim.py 早已在用 Wilder ADX（L314-321 兼容入口委托 core.indicators；
L744-745 EVENT 腿门 = adx14_of(bs,i) 配 adx>=20）与 CFG.MAX_HOLD=12。
本文件不改变任何生产行为，只使回测数字首次可信地代表生产实际执行。

重基线证据（R38 研究循环，§97.18-97.20）:
  冻结基线(legacy DX, h15): n=1974 avg+3.83% PF3.08 MDD-629 OOS PF3.48
  本基线(Wilder, h12):       n=1547 avg+3.85% PF3.72 MDD-448 OOS PF4.03
  → PF +0.64 / MDD +181pp / OOS PF +0.55 / RR<=-1R 19.6→19.2%

历史基线归档: research/archive/combo_v20f_trades_legacy_dx_h15.csv
（旧 n=1974 保留作对照，不得删除；旧生成器 gen_v20f.py 保留但已标注废弃）

任何新代码需要 ADX 时只允许 import core.indicators.adx14_of。"""
import csv, io, json, os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.events import classify_title
from core.indicators import adx14_of as wilder_adx14     # ← 修正① P1-7
from core.structure import structure_events               # ← R57: 因果结构事件流(单源)
import config as CFG                                      # ← 修正② P1-8: MAX_HOLD
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def board_of(code):
    """R57(v21 §A): 板块分类 — R38 证据(20%制度溢价)落列。"""
    if code.startswith("60"): return "SH_MAIN"
    if code.startswith(("000", "001", "002", "003")): return "SZ_MAIN"
    if code.startswith("30"): return "CYB"
    if code.startswith("68"): return "KCB"
    if code[:1] in ("4", "8"): return "BSE"
    return "OTHER"


def struct_columns(bs, i, ep, tp2, sl1):
    """R57(v21 §A): 信号日 i 因果结构上下文列。全部只用 <=i 的已确认信息。"""
    evs = structure_events(bs, i)
    last = evs[-1] if evs else None
    broken_low = None
    for e in reversed(evs):
        if e["kind"].endswith("↓"):
            broken_low = e["level"]
            break
    layers = 0
    near = None
    for k in range(max(2, i - 60), i + 1):
        if bs[k]["h"] < bs[k - 2]["l"]:  # bearish FVG 形成于信号日前60bar内
            top, bot = bs[k - 2]["l"], bs[k]["h"]
            if bot < tp2 * 1.05 and top > ep:
                layers += 1
                if near is None or bot < near:
                    near = bot
    w90 = bs[max(0, i - 89):i + 1]
    hi90 = max(b["h"] for b in w90)
    lo90 = min(b["l"] for b in w90)
    eq90 = (hi90 + lo90) / 2
    zone = "premium" if ep > eq90 * 1.02 else ("discount" if ep < eq90 * 0.98 else "equilibrium")
    return {
        "trend_state": last["trend"] if last else "none",
        "last_event_kind": last["kind"] if last else "",
        "last_event_date": last["date"] if last else "",
        "last_event_level": round(last["level"], 3) if last else "",
        "event_gap_bars": (i - last["bar"]) if last else "",
        "broken_low_level": round(broken_low, 3) if broken_low else "",
        "sl_below_structure": (1 if (broken_low and sl1 is not None and sl1 < broken_low) else 0),
        "supply_layers": layers,
        "nearest_supply_dist": round((near / ep - 1) * 100, 2) if near else "",
        "zone_90d": zone,
    }

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
bar_cache = {}
def bars_of(code):
    if code not in bar_cache:
        p = code2file.get(code)
        if not p:
            bar_cache[code] = []
            return bar_cache[code]
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def is_strong(title):
    """统一委托 core.events.classify_title —— 回测/生产同一套事件分类。"""
    is_ev, kind, pol, _amt, _pct = classify_title(title)
    return bool(is_ev and pol > 0)


def adx14(bs, i):
    """修正①(P1-7): 委托 core.indicators.adx14_of(标准 Wilder 平滑 ADX)，
    替代 legacy 单窗 DX —— 与生产 paper_sim EVENT 腿口径一致。"""
    return wilder_adx14(bs, i)


def stage_of(bs, i):
    if i < 91:
        return None
    w60 = bs[i - 60:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in bs[i - 20:i]) / 20
    v60 = sum(b["v"] for b in bs[i - 60:i]) / 60
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    return "UPTREND" if ret60 > 0 else "DOWNTREND"


def weekly_trend_of(bs, i):
    closes = []
    j = i
    while j >= 0 and len(closes) < 20:
        closes.append(bs[j]["c"])
        j -= 5
    closes.reverse()
    if len(closes) < 12:
        return None
    ma10 = sum(closes[-10:]) / 10
    ma_prev = sum(closes[-12:-2]) / 10
    return "up" if ma10 > ma_prev else "down"


ev = []
seen = set()
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
for date, code, title in cur.fetchall():
    if not is_strong(title):
        continue
    d = str(date)[:10].replace("-", "")
    if (code, d) in seen:
        continue
    seen.add((code, d))
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if d not in dates:
        continue
    i = dates.index(d)
    st = stage_of(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    entry_idx = i + 1
    if entry_idx + 17 >= len(bs) or entry_idx < 130:
        continue
    if bs[entry_idx]["t"] < "20230901":
        continue
    ep_open = bs[entry_idx]["o"]
    disc_close = bs[i]["c"]
    if ep_open <= 0:
        continue
    avg_v = sum(bs[k]["v"] for k in range(i - 19, i + 1)) / 20 if i >= 19 else 0
    # FIX(2026-08-22): 无泄漏 —— v_ratio 用 T 日量（披露日收盘可得，决策时点），v2_ratio 用 T-1 量
    v_ratio = bs[i]["v"] / avg_v if avg_v > 0 else 1.0
    v2_ratio = bs[i - 1]["v"] / avg_v if (avg_v > 0 and i >= 1) else 0
    stage_span = 0
    for j in range(i, max(0, i - 60), -1):
        if stage_of(bs, j) == st:
            stage_span += 1
        else:
            break
    adx_span = 0
    for j in range(i, max(0, i - 40), -1):
        if (adx14(bs, j) or 0) >= 20:
            adx_span += 1
        else:
            break
    wt = weekly_trend_of(bs, i)
    # FIX(2026-08-22): rank_score 特征对齐（7↔7 与 paper_sim 一致）—— 加事件类型 +1
    _etype = 1 if ("方案" in str(title) or "首次" in str(title) or "计划" in str(title)) else 0
    rs = (2 if st == "ACCUM" else 1)
    rs += (1 if v_ratio > 1.2 else 0) + (1 if v_ratio >= 2.0 else 0)
    rs += (1 if 6 <= stage_span <= 15 else 0) + (1 if adx_span > 15 else 0)
    rs += 1 if wt == "down" else 0
    rs += 1 if (v_ratio >= 1.5 and v2_ratio >= 1.5) else 0
    rs += _etype
    highs = []
    lows = []
    for j in range(i - 1, max(0, i - 60), -1):
        if j < 3 or j + 3 >= i:
            continue
        if len(highs) < 2 and bs[j]["h"] > max(bs[k]["h"] for k in range(j - 3, j)) and bs[j]["h"] >= max(bs[k]["h"] for k in range(j + 1, j + 4)):
            highs.append(bs[j]["h"])
        if len(lows) < 2 and bs[j]["l"] < min(bs[k]["l"] for k in range(j - 3, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + 4)):
            lows.append(bs[j]["l"])
        if len(highs) >= 2 and len(lows) >= 2:
            break
    if not highs or not lows:
        continue
    highs.sort()
    # retrace entry (回踩买点 ×0.99)
    limit = disc_close * 0.99
    ep = limit if bs[entry_idx]["l"] <= limit else ep_open
    # tiered TP/SL exit
    tp1, tp2, tp3 = highs[0], (highs[1] if len(highs) > 1 else highs[0] * 1.05), highs[-1]
    # SL = sweep low − 0.5×ATR（A股可执行，P1 已落地模拟器）
    _atr = 0
    if i >= 15:
        _trs = []
        for _k in range(i - 14, i):
            _tr = max(bs[_k]["h"] - bs[_k]["l"], abs(bs[_k]["h"] - bs[_k - 1]["c"]), abs(bs[_k]["l"] - bs[_k - 1]["c"]))
            _trs.append(_tr)
        _atr = sum(_trs) / 14 if _trs else 0
    sl1 = (lows[0] - 0.5 * _atr) if _atr > 0 else lows[0] * 0.99
    # P2: TP 单调去重（确保 tp1<tp2<tp3 且都 > ep）
    _tps = sorted([x for x in (tp1, tp2, tp3) if x and x > ep])
    if not _tps:
        continue
    tp1 = _tps[0]
    tp2 = _tps[1] if len(_tps) > 1 else tp1 * 1.05
    tp3 = _tps[2] if len(_tps) > 2 else tp2 * 1.05
    # 退出委托 core.execution.simulate（tp1 30%部分+保本/tp2/tp3 runner/持有期）
    from core.execution import simulate as _sim
    # 修正②(P1-8): max_hold 15 → CFG.MAX_HOLD(12)，与生产统一退出持有期
    _r = _sim(bs, entry_idx, ep, sl1, tp1=tp1, tp2=tp2, tp3=tp3,
              partial_tp1=0.3, stop_to_be=True, max_hold=CFG.MAX_HOLD, code=code[:6])
    net = _r.get("net_pnl_pct", 0.0)
    if _r.get("skipped"):
        continue  # BAD_ENTRY(ep<sl 非法区间几何) / SKIP_LIMIT_UP(一字涨停) —— 非真实交易，跳过
    # 事件腿逐笔明细 —— 从 simulate 结果补齐 buy/sell/hold/reason/TP-SL/MFE-MAE
    _risk = ep - sl1
    _hb = _r.get("hold_bars", 0)
    _sell_i = min(len(bs) - 1, entry_idx + max(1, _hb)) if _hb else entry_idx
    # R57(v21): 结构上下文 + 决策透明化列 —— 全部信号日因果, 引擎行为零变化
    _sc = struct_columns(bs, i, ep, tp2, sl1)
    _comp = {"stage": 2 if st == "ACCUM" else 1,
             "vr1": 1 if v_ratio > 1.2 else 0, "vr2": 1 if v_ratio >= 2.0 else 0,
             "span": 1 if 6 <= stage_span <= 15 else 0, "adx": 1 if adx_span > 15 else 0,
             "wt_down": 1 if wt == "down" else 0,
             "vol_cont": 1 if (v_ratio >= 1.5 and v2_ratio >= 1.5) else 0, "etype": _etype}
    _subs = [{"name": "披露日", "date": d, "detail": str(title)[:40]},
             {"name": "入场(T+1)", "date": bs[entry_idx]["t"], "detail": "次日开盘/回踩0.99限价"}]
    ev.append({
        "symbol": code + (".SH" if code.startswith("6") else ".SZ"), "entry_date": bs[entry_idx]["t"],
        "src": "EVENT",
        "buy_date": bs[entry_idx]["t"], "buy_price": round(ep, 3),
        "sell_date": bs[_sell_i]["t"] if _hb else "",
        "sell_price": round(_r.get("exit_price", 0), 3) if _hb else "",
        "reason": _r.get("reason", ""), "hold_bars": _hb,
        "tp": round(tp2, 3), "sl": round(sl1, 3), "risk_pct": round(_risk / ep * 100, 3) if _risk > 0 else 0,
        "net_pnl_pct": round(net, 4),
        "mfe_pct": _r.get("mfe_pct", 0), "mae_pct": _r.get("mae_pct", 0),
        "mfe_r": _r.get("mfe_r", 0), "mae_r": _r.get("mae_r", 0),
        "rr_exit": round((_r.get("exit_price", ep) / ep - 1) / (_risk / ep), 3) if _risk > 0 else 0,
        "signal_chain": "insider-event", "r20": "", "rank": rs,
        "board": board_of(code[:6]), **_sc,
        "stage_span": stage_span, "adx_span": adx_span,
        "sub_signals": json.dumps(_subs, ensure_ascii=False),
        "rank_components": json.dumps(_comp)})
conn.close()
print("事件(v20f2 Wilder+h12):", len(ev))

# continuation (P2-1: VWAP10% + 支撑新鲜度≤5, from cont_v20f_new.csv)
cont = []
with open(r"E:\test\smc_project\research\cont_v20f_new.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        cont.append({"symbol": r.get("symbol"), "entry_date": r.get("entry_date"),
                     "src": "CONT", "net_pnl_pct": float(r["net_pnl_pct"]), "rank": 3})

# dedup
seen_c = set()
combo = []
for t in ev + cont:
    k = (str(t["symbol"]), str(t["entry_date"]))
    if k in seen_c:
        continue
    seen_c.add(k)
    combo.append(t)

# FIX(2026-09-05, 审计集中度): 按月 cap=500 分散约束 —— 202402 单月曾占 31.2%（1433笔），
# 单月极端行情主导收益。保留每月 rank 最高的前 500 笔，显著降低集中风险。
COMBO_MONTH_CAP = 500
from collections import defaultdict
by_month_combo = defaultdict(list)
for t in combo:
    by_month_combo[str(t["entry_date"])[:6]].append(t)
combo_capped = []
for m, v in sorted(by_month_combo.items()):
    v_sorted = sorted(v, key=lambda t: -(float(t.get("rank") or 0)))
    combo_capped.extend(v_sorted[:COMBO_MONTH_CAP])
combo = combo_capped

# R57(v21): CONT 腿补结构列(趋势/事件/板块 causal; 供给与SL列留空 — CONT无tp/sl锚)
for t in cont:
    code6 = str(t.get("symbol") or "")[:6]
    if not code6:
        continue
    bs2 = bars_of(code6)
    if not bs2:
        continue
    dts2 = [b["t"] for b in bs2]
    ed2 = str(t.get("entry_date") or "")
    if ed2 not in dts2:
        continue
    i2 = dts2.index(ed2) - 1
    if i2 < 95:
        continue
    evs2 = structure_events(bs2, i2)
    last2 = evs2[-1] if evs2 else None
    _c2 = bs2[i2]["c"]
    _w2 = bs2[max(0, i2 - 89):i2 + 1]
    _eq2 = (max(b["h"] for b in _w2) + min(b["l"] for b in _w2)) / 2
    t.update({"board": board_of(code6),
              "trend_state": last2["trend"] if last2 else "none",
              "last_event_kind": last2["kind"] if last2 else "",
              "last_event_date": last2["date"] if last2 else "",
              "last_event_level": round(last2["level"], 3) if last2 else "",
              "event_gap_bars": (i2 - last2["bar"]) if last2 else "",
              "broken_low_level": "", "sl_below_structure": "",
              "supply_layers": "", "nearest_supply_dist": "",
              "zone_90d": ("premium" if _c2 > _eq2 * 1.02 else ("discount" if _c2 < _eq2 * 0.98 else "equilibrium")),
              "stage_span": "", "adx_span": "", "sub_signals": "", "rank_components": ""})

# R57(v21): 写 combo_v21_trades.csv —— 不触碰 canonical(v20f 冻结基线)
V21_FIELDS = ["symbol", "entry_date", "src", "net_pnl_pct", "rank",
              "buy_date", "buy_price", "sell_date", "sell_price",
              "reason", "hold_bars", "tp", "sl", "risk_pct",
              "mfe_pct", "mae_pct", "mfe_r", "mae_r", "rr_exit",
              "signal_chain", "r20",
              "board", "trend_state", "last_event_kind", "last_event_date",
              "last_event_level", "event_gap_bars", "broken_low_level",
              "sl_below_structure", "supply_layers", "nearest_supply_dist",
              "zone_90d", "stage_span", "adx_span", "sub_signals", "rank_components"]
out_path = r"E:\test\smc_project\research\combo_v21_trades.csv"
with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=V21_FIELDS, restval="", extrasaction="ignore")
    w.writeheader()
    for t in combo:
        w.writerow(t)
print(f"v21 结构增强 CSV(引擎=v20f2 零改动, 仅加列): {len(combo)} 笔 → {out_path}")

# quick stats
import statistics
# FIX(2026-09-04, 审计 P2 幸存者偏差): 回测仅覆盖当前缓存中有 K 线的股票（退市/长期停牌股被排除），
# 存在正向幸存者偏差。此处提供"剔除极端尾部(net<=-50%，疑似退市/暴跌)"对照，量化偏差影响。
for y in ("2024", "2025", "2026"):
    ys = [t for t in combo if str(t["entry_date"])[:4] == y]
    if ys:
        pnls = [t["net_pnl_pct"] for t in ys]
        wins = [x for x in pnls if x > 0]
        pf = sum(wins) / abs(sum(x for x in pnls if x <= 0)) if any(x <= 0 for x in pnls) else 99
        # 剔除尾部对照
        pnls_c = [x for x in pnls if x > -50.0]
        wins_c = [x for x in pnls_c if x > 0]
        pf_c = sum(wins_c) / abs(sum(x for x in pnls_c if x <= 0)) if any(x <= 0 for x in pnls_c) else 99
        n_tail = len(pnls) - len(pnls_c)
        print(f"  {y}: n={len(ys)} avg={sum(pnls)/len(pnls):+.2f}% PF={pf:.2f} | 剔除尾部后 n={len(pnls_c)} avg={sum(pnls_c)/len(pnls_c):+.2f}% PF={pf_c:.2f} (剔除{n_tail}笔 net<=-50%)")
print("注: 回测存在正向幸存者偏差（仅覆盖现存股票），剔除尾部对照供参考。")
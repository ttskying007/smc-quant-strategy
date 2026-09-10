# -*- coding: utf-8 -*-
"""v4_d1_shadow_portfolio.py —— V3-B 前置: E 系数组合层双臂预演(离线, 预注册)
目的: E-score 进组合层(DailyPortfolioEngine)的双臂对照, 先在离线回放上预演,
SHADOW 实盘对照仍按 60 日双臂计划不变。
设计: 事件腿 1640 笔(EVENT csv) × E(决策时点, escore_history_full 单源)
  双臂 = 同一信号流, 同一引擎, 唯一差异 = position_pct × exposure_coef(E):
    ARM_BASE : position_pct = 8%(固定)
    ARM_E    : position_pct = 8% × coef(E) (Q1→0.3 ... 黄金→1.0; E缺失→1.0)
  组合约束(生产语义): max_total_exposure=0.8, max_single=0.25, max_daily_opens=5,
    kill(权益日差-3%, 2交易日), TTL 5 日, fill_or_open=True(事件腿语义),
    fee 0.2%, slippage 0.1%。
  市场数据: K 线缓存逐日喂 on_day(只喂持仓/挂单涉及的股票 —— 简化: 每日全组合股票)。
预注册判定:
  P1 E臂权益终值 > 基线 且 E臂 MDD 更小 → E 系数组合层增益(两降一升)
  P2 E臂 PF ≥ 基线 −0.2 且 WR 不降超 5pp → 不以质量换数量
  P3 n_filled 双臂差 <10%(E 不杀单只降仓)
输出: handover/V4_D1_组合层双臂预演.json"""
import csv, glob, io, json, os, sys, time
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.portfolio import DailyPortfolioEngine
from core.escore import exposure_coef

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
FEE_SLIP = dict(fee_pct=0.2, slippage_pct=0.1)
BASE_POS = 0.08
OOS = "20250701"

# ---- E 全历史快照(单源) ----
E_HIST = {}
for _p in (r"E:\test\smc_project\research\handover\escore_history_full.json",
           r"E:\test\smc_project\research\handover\escore_history.json"):
    try:
        _h = json.load(open(_p, encoding="utf-8"))
        _d = {x["d8"]: x.get("e") for x in _h.get("days", []) if x.get("e") is not None}
        if len(_d) > len(E_HIST):
            E_HIST = _d
    except Exception:
        pass
print(f"E 快照: {len(E_HIST)} 日")

# ---- 信号流(EVENT csv → 逐日订单) ----
rows = [r for r in csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv",
                                       encoding="utf-8-sig")) if r.get("src") == "EVENT"]
signals = defaultdict(list)     # signal_date -> [(code, entry_limit, sl, tp, bars)]
sl_fixed = 0.07                 # 事件腿 SL 7%(R2 结论: 窄 SL 有害, 用宽基线)
for r in rows:
    d8 = r["entry_date"]
    try:
        bp = float(r["buy_price"])
    except Exception:
        continue
    if bp <= 0:
        continue
    lim = round(bp * 0.99, 4)          # 事件腿限价 = 0.99×信号日收盘(生产语义)
    signals[d8].append({"code": r["symbol"].split(".")[0], "entry_limit": lim,
                        "sl": round(bp * (1 - sl_fixed), 4),
                        "tp": round(bp * (1 + 3 * sl_fixed), 4)})

# ---- K 线按日索引(code → daily 列表), 惰性加载 ----
_daily_cache = {}
def get_daily(code):
    if code in _daily_cache:
        return _daily_cache[code]
    for suf in ("_SZ", "_SH", "_BJ"):
        fp = os.path.join(KT, f"{code}{suf}_daily_800.json")
        if os.path.exists(fp):
            try:
                raw = json.load(open(fp, encoding="utf-8"))
                d = [{"t": str(b["t"])[:8], "o": float(b["o"]), "h": float(b["h"]),
                      "l": float(b["l"]), "c": float(b["c"])} for b in raw]
                _daily_cache[code] = d
                return d
            except Exception:
                break
    _daily_cache[code] = []
    return []

def run_arm(use_e):
    eng = DailyPortfolioEngine(1_000_000, max_total_exposure=0.8, max_single=0.25,
                               max_daily_opens=5, kill_daily_loss=0.03, kill_days=2,
                               max_sector=3, **FEE_SLIP)
    active_codes = {s["code"] for lst in signals.values() for s in lst}
    # 涉及股票的全日历
    dates = sorted(signals.keys())
    d_lo = min(dates)
    # 订单提交日历: 信号日收盘提交, 次日起撮合(fill_or_open 事件腿语义)
    by_date = defaultdict(list)
    for d8, lst in signals.items():
        for s in lst:
            by_date[d8].append(s)
    all_dates = sorted({b["t"] for c in active_codes for b in get_daily(c)
                        if b["t"] >= d_lo and b["t"] <= "20260910"})
    for d8 in all_dates:
        for s in by_date.get(d8, []):
            e = E_HIST.get(d8)
            coef = exposure_coef(e) if use_e else 1.0
            eng.submit_order({"code": s["code"], "entry_limit": s["entry_limit"],
                              "sl": s["sl"], "tp": s["tp"], "bars_max": 15,
                              "position_pct": BASE_POS * coef, "fill_or_open": True,
                              "signal_date": d8, "max_pending_days": 5})
        # 当日市场(只喂涉及的持仓+挂单股票)
        mkt = {}
        for o in eng.orders:
            d = get_daily(o["code"])
            b = next((x for x in d if x["t"] == d8), None)
            if b:
                mkt[o["code"]] = b
        for c, p in eng.positions.items():
            if c not in mkt:
                d = get_daily(c)
                b = next((x for x in d if x["t"] == d8), None)
                if b:
                    mkt[c] = b
        if mkt:
            eng.on_day(d8, mkt)
    return eng

t0 = time.time()
print("ARM_BASE(固定8%)...", flush=True)
eng_base = run_arm(False)
print(f"  {time.time()-t0:.0f}s")
print("ARM_E(系数降仓)...", flush=True)
eng_e = run_arm(True)
print(f"  {time.time()-t0:.0f}s")

sb, se = eng_base.summary(), eng_e.summary()
n_b, n_e = sb["n_trades"], se["n_trades"]
tl_b = eng_base.trade_log
tl_e = eng_e.trade_log
def pf_of(tl):
    w = sum(t["ret_pct"] for t in tl if t["ret_pct"] > 0)
    l_ = abs(sum(t["ret_pct"] for t in tl if t["ret_pct"] <= 0))
    return round(w / l_, 2) if l_ else 99.0
def wr_of(tl):
    return round(len([t for t in tl if t["ret_pct"] > 0]) / len(tl) * 100, 1) if tl else None

delta_ret = round(se["total_return_pct"] - sb["total_return_pct"], 2)
mdd_improve = round(sb["mdd_pct"] - se["mdd_pct"], 2)
verdict = {
    "P1_权益更高且MDD更小": se["total_return_pct"] > sb["total_return_pct"] and se["mdd_pct"] < sb["mdd_pct"],
    "P2_PF不降超0.2且WR不降超5pp": (pf_of(tl_e) >= pf_of(tl_b) - 0.2
                                  and (wr_of(tl_e) or 0) >= (wr_of(tl_b) or 0) - 5),
    "P3_n差<10%": abs(n_e - n_b) / max(n_b, 1) < 0.10,
}
out = {"arms": {"BASE": {**sb, "pf": pf_of(tl_b), "wr": wr_of(tl_b)},
                "E_coef": {**se, "pf": pf_of(tl_e), "wr": wr_of(tl_e)}},
       "delta_total_return_pp": delta_ret, "mdd_improvement_pp": mdd_improve,
       "config": {"base_pos": BASE_POS, "sl_fixed": sl_fixed,
                  "coef_map": "Q1→0.3 / Q2→0.5 / Q3→0.75 / Q4+→1.0 / E缺→1.0"},
       "preregistered": verdict,
       "note": "离线预演(事件腿信号流回放); SHADOW 60日实盘对照另行"}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_D1_组合层双臂预演.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"BASE : ret={sb['total_return_pct']}% mdd={sb['mdd_pct']}% n={n_b} pf={pf_of(tl_b)} wr={wr_of(tl_b)}")
print(f"E    : ret={se['total_return_pct']}% mdd={se['mdd_pct']}% n={n_e} pf={pf_of(tl_e)} wr={wr_of(tl_e)}")
print(f"Δret={delta_ret}pp  MDD改善={mdd_improve}pp")
print("预注册:", json.dumps(verdict, ensure_ascii=False))
print("已写 handover/V4_D1_组合层双臂预演.json")
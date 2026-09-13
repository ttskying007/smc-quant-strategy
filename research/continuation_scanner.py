# -*- coding: utf-8 -*-
"""延续腿 scanner 集成：扫描当前 MARKUP 结构支撑 + VWAP10% + 低波动 信号
（v20c 生产 = 反转 + 延续；scanner 需输出延续候选。VWAP 5%->10% 于 2026-08-22 优化）"""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as CFG  # 审计 P1: 统一路径
# FIX(2026-09-13, 第七轮审计 P1-5): 生产硬编码 → config.py 统一路径(WDH_DIR)
sys.path.insert(0, CFG.WDH_DIR)
import wdh_engine as we

KT = CFG.KT_CACHE
PIVOT = 3


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            out.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
    out.sort(key=lambda b: b["t"])
    return out


def is_swing_low(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["l"] < min(bs[k]["l"] for k in range(j - PIVOT, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + PIVOT + 1))


def stage_detailed(bs, i):
    if i < 61:
        return None
    w60 = bs[i - 60:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(x["v"] for x in bs[i - 20:i]) / 20
    v60 = sum(x["v"] for x in bs[i - 60:i]) / 60
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    if ret60 > 0:
        return "UPTREND"
    return "DOWNTREND"


# global median vol20 (computed once from fresh files)
def compute_median():
    vols = []
    for p in os.listdir(KT):
        if not p.endswith("_daily_800.json"):
            continue
        daily = bars(os.path.join(KT, p))
        if len(daily) < 80:
            continue
        w20 = daily[-21:-1] if len(daily) >= 21 else daily
        if len(w20) == 20:
            vols.append(sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20)
        if len(vols) > 3000:
            break
    vols.sort()
    return vols[len(vols) // 2]


V_MED = compute_median()
print(f"vol20 中位: {V_MED:.4f}", flush=True)

# FIX(2026-09-08, 审计 P0-3): 交易日历（惰性构建）—— 仅在出现候选需计算 next_td 时才扫描全市场。
# 避免每次运行都多读一遍 ~4551 个 K 线文件（IO 翻倍）。
_ALL_TRADE_DATES = None


def next_trade_day(d8):
    """返回 d8 之后第一个已收盘交易日（为 valid_from 提供明日开盘日）。惰性构建日历。"""
    global _ALL_TRADE_DATES
    if not d8:
        return ""
    if _ALL_TRADE_DATES is None:
        _s = set()
        for _p in sorted(os.listdir(KT)):
            if not _p.endswith("_daily_800.json"):
                continue
            for _b in bars(os.path.join(KT, _p)):
                _s.add(_b["t"])
        _ALL_TRADE_DATES = _s
    for d in sorted(_ALL_TRADE_DATES):
        if d > d8:
            return d
    return ""

# scan for continuation candidates at latest bar (entry next trade day)
cands = []
n = 0
latest = ""
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    if daily[-1]["t"] > latest:
        latest = daily[-1]["t"]
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    # FIX(2026-09-08, 审计 P0-3): 消除延续腿前视/滞后混用。
    # 原实现 `i = len-2`(信号倒数第二根), `entry_idx = i+1 = 最后根`，
    # 且 VWAP/vol/entry_price 用到 entry_idx(最后根)的 open/close/volume ——
    # 这些在"以最后根收盘后、次日开盘前"做选股时均不可知。
    # 改为：signal_idx = len-1(最新已收盘日)，所有特征只算到 signal_idx，
    # entry 为下一个交易日(明日开盘)由 paper_sim.monitor 以实时 open 撮合，不写历史成交价。
    i = len(daily) - 1
    st = stage_detailed(daily, i)
    if st != "MARKUP":
        continue
    sl_tmp = None
    sl_idx = None
    # FIX(2026-09-05, 审计 F04): 摆动低点确认须在信号bar(i)之前完成 —— j + PIVOT <= i，
    # 否则用了 i+1（入场根）之后的K线确认（回测/实盘信号集不一致）。
    for j in range(i, PIVOT - 1, -1):
        if j + PIVOT > i:
            continue
        if is_swing_low(daily, j):
            sl_tmp = daily[j]["l"]
            sl_idx = j
            break
    if sl_tmp is None:
        continue
    # FIX(2026-08-22) P2: 支撑新鲜度 ≤5 天（研究：>5 天负收益 -2.43%）
    if sl_idx is not None and (i - sl_idx) > 5:
        continue
    if not (daily[i]["l"] <= sl_tmp * 1.01 and daily[i - 1]["c"] > sl_tmp):
        continue
    if daily[i]["c"] <= sl_tmp:
        continue
    # FIX(2026-09-08, 审计 P0-3): 引用价 = signal 收盘（决策时点可得），成交由 monitor 以次日 real open 撮合
    ref_px = daily[i]["c"]
    if sl_tmp >= ref_px:
        continue
    # VWAP/vol 只算到 signal_idx（不含未来 entry 日）
    pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(i - 19, i + 1))
    vol = sum(daily[k]["v"] for k in range(i - 19, i + 1))
    if vol <= 0:
        continue
    vw = pv / vol
    # FIX(2026-08-22): VWAP threshold 5% -> 10% (research: monotonic improvement, 10% = +8.56%)
    # FIX(2026-09-13, 第八轮审计 5.9): 0.09 → 0.10 —— 与 paper_sim.sub_signals_cont()
    # 及注释口径统一(原 9% 使生产 scanner 信号集与回测/文档不一致, 审计 §5.9)。
    if (daily[i]["c"] - vw) / vw < 0.10:
        continue
    w20 = daily[i - 20:i]
    vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20 if len(w20) == 20 else 0
    if vol20 >= V_MED:
        continue
    cands.append({"symbol": sym, "signal_date": daily[i]["t"],
                  # FIX(2026-09-08, 审计 P0-3): entry 为下一交易日（明日），不提前写死历史 entry 价。
                  # entry_price 改为 signal 收盘参考价，成交由 paper_sim 实时 open 撮合。
                  "entry_date": next_trade_day(daily[i]["t"]), "valid_from": next_trade_day(daily[i]["t"]),
                  "entry_mode": "next_open",
                  "reference_price": round(ref_px, 3), "entry_price": round(ref_px, 3),
                  "support": round(sl_tmp, 3),
                  "hold": 10, "signal": "CONTINUATION_MARKUP", "stage": "MARKUP"})
    if n % 1500 == 0:
        print(f"  {n} files, cands {len(cands)}", flush=True)

print(f"扫描完成: {n} files, latest={latest}, 延续候选(阈值10%): {len(cands)}")
# FIX(2026-09-13, 第八轮审计 5.9): freshness gate —— 与 current_scanner 同语义,
# 每只候选股最新 bar 必须等于全市场最新交易日(旧数据不产生延续信号, 审计 §5.9:
# "可能旧数据产生延续信号")。两阶段: 全市场 latest 已在循环中收集, 此处过滤。
_n_before = len(cands)
cands = [c for c in cands if c.get("signal_date") == latest]
_dropped = _n_before - len(cands)
if _dropped:
    print(f"freshness gate: 剔除 {_dropped} 个旧数据候选(signal_date != {latest})")
for c in cands[:10]:
    print(f"  {c['symbol']}: signal={c['signal_date']} ref={c['reference_price']} support={c['support']}")

# merge into scanner result
# FIX(2026-09-13, 第七轮审计 P1-5): 生产硬编码 → config.py 统一路径(RESEARCH_DIR)
_CSR = os.path.join(CFG.RESEARCH_DIR, "current_scanner_result.json")
try:
    with open(_CSR, encoding="utf-8") as fh:
        res = json.load(fh)
except Exception:
    res = {}
res["continuation_candidates"] = cands
res["continuation_count"] = len(cands)
res["latest_date"] = latest
with open(_CSR, "w", encoding="utf-8") as fh:
    json.dump(res, fh, ensure_ascii=False, indent=2)
print("scanner result updated with continuation candidates")

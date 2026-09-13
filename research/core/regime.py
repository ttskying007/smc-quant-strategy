# -*- coding: utf-8 -*-
"""core/regime.py —— V2 ITERATION 6: Market Regime 真值层
蓝图 §31-33: 替代幸存者偏差的 200 股 proxy → 指数真值。
输入: 上证指数(000001_SH) + 沪深300(000300_SH) 日线(决策时点可得, 无前视)。
输出六态: BULL / BEAR / SIDEWAYS / PANIC / RECOVERY / ROTATION

规则(研究起点, 蓝图 §32 全要素受数据可用性约束的简化实现):
  - 趋势: 指数20日均线 vs 60日均线 + 20日收益符号
  - 波动: 20日 ATR% 相对其 120日分位
  - PANIC:  20日收益 < -8% 或 ATR% 分位 > 90% 且 20日收益<0
  - RECOVERY: 从 BEAR/PANIC 转换后 20日收益>0 且仍低于 60日高点
  - BULL:   20MA>60MA 且 20日收益>0
  - BEAR:   20MA<60MA 且 20日收益<-3%
  - SIDEWAYS: 其余
  - ROTATION: 指数横盘但 300 vs 上证 20日收益差 |>3%| (大小盘轮动)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as CFG

# FIX(2026-09-13, 第七轮审计 P1-5): 生产硬编码 → config.py 派生路径(ETF 指数缓存)
KT_CACHE = os.path.join(CFG.HERMES_DIR, "kline_cache_etf")


def _load_index(fn):
    fp = os.path.join(KT_CACHE, fn)
    if not os.path.exists(fp):
        return None
    raw = json.load(open(fp, encoding="utf-8"))
    out = []
    for b in raw:
        t = str(b.get("t") or b.get("date") or "")[:10]
        t = t.replace("-", "")  # '2024-04-12' → '20240412'
        if t.isdigit() and len(t) == 8:
            out.append((t, float(b["c"]), float(b.get("h") or b["c"]), float(b.get("l") or b["c"])))
    out.sort(key=lambda x: x[0])
    return out


def market_regime(d8):
    """决策时点 d8(YYYYMMDD) 的市场状态六态。
    返回 {regime, sh20, sh_atr_pct, hs300_20, spread, components}。"""
    sh = _load_index("000001_SH_day.json")
    hs = _load_index("000300_SH_day.json")
    if not sh:
        return None
    # d8 及之前的指数数据
    sh_w = [x for x in sh if x[0] <= d8]
    if len(sh_w) < 70:
        return None
    closes = [x[1] for x in sh_w]
    r20 = closes[-1] / closes[-21] - 1 if len(closes) >= 21 else 0
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    # ATR% 分位(120日)
    trs = []
    for k in range(max(1, len(sh_w) - 120), len(sh_w)):
        c_prev = sh_w[k - 1][1]
        trs.append(max(sh_w[k][2] - sh_w[k][3], abs(sh_w[k][2] - c_prev), abs(sh_w[k][3] - c_prev)))
    atr_pct = (sum(trs) / len(trs)) / closes[-1] * 100 if trs else 0
    atr_rank = sum(1 for x in trs if x <= trs[-1]) / len(trs) if trs else 0.5
    # 距60日高点
    high60 = max(closes[-60:])
    off_high = closes[-1] / high60 - 1
    # 300 vs 上证轮动
    spread = None
    if hs:
        hs_w = [x for x in hs if x[0] <= d8]
        if len(hs_w) >= 21:
            hs20 = hs_w[-1][1] / hs_w[-21][1] - 1
            spread = hs20 - r20
    # 判定顺序: PANIC > BEAR > BULL > RECOVERY > ROTATION > SIDEWAYS
    if r20 < -0.08 or (atr_rank > 0.9 and r20 < 0):
        regime = "PANIC"
    elif ma20 < ma60 and r20 < -0.03:
        regime = "BEAR"
    elif ma20 > ma60 and r20 > 0:
        regime = "BULL"
    elif r20 > 0 and off_high < 0:
        regime = "RECOVERY"
    elif spread is not None and abs(spread) > 0.03:
        regime = "ROTATION"
    else:
        regime = "SIDEWAYS"
    return {"regime": regime, "sh_r20": round(r20 * 100, 2), "atr_pct": round(atr_pct, 2),
            "atr_rank": round(atr_rank, 2), "off_high": round(off_high * 100, 2),
            "hs300_sh_spread": round(spread * 100, 2) if spread is not None else None,
            "asof": d8}


def regime_effect_on_event_leg(trades_by_date):
    """事件腿在六态下的表现分布(研究接口: 输入 {d8: [net,...]}, 输出各regime统计)。"""
    buckets = {}
    for d8, nets in trades_by_date.items():
        rg = market_regime(d8)
        if not rg:
            continue
        buckets.setdefault(rg["regime"], []).extend(nets)
    out = {}
    for reg, nets in buckets.items():
        w = [x for x in nets if x > 0]
        l_ = [x for x in nets if x <= 0]
        out[reg] = {"n": len(nets), "avg": round(sum(nets) / len(nets), 3),
                    "wr": round(len(w) / len(nets), 3),
                    "pf": round(sum(w) / abs(sum(l_)), 2) if l_ and sum(l_) < 0 else 99}
    return out
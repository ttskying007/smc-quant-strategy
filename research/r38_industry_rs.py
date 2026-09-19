# -*- coding: utf-8 -*-
"""步骤 8: 行业相对强弱(Relative Strength)
数据源:
  - hermes/data/industry_map.json → sym → industry(证监会行业, 5530 股)
  - hermes/kline_cache_tencent/{sym}_daily_800.json 近 800 日个股日线
  - hermes/kline_cache_etf/000001_SH_day.json 指数基准(上证)
指标(参考 Stockbee / Mark Minervini):
  - RS20: 行业 20 日均收益 - 上证 20 日收益(绝对差, 单位%)
  - RS60: 同上但 60 日
  - N_count: 行业内样本数(覆盖度辅助, 样本<5 → skip)
用途:
  - 选股阶段加一层"先选强板块再选强个股"的过滤(V2 §8 蓝图要求)
  - 与 event 腿(rank/adx/stage)联用可解释 E-score 波动来源
用法: python research/r38_industry_rs.py --days 20
"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as CFG
from collections import defaultdict
import statistics

KT = os.path.join(CFG.RESEARCH_DIR, "..", "hermes", "kline_cache_tencent")
ETF = os.path.join(CFG.RESEARCH_DIR, "..", "hermes", "kline_cache_etf")
MAP = os.path.join(CFG.RESEARCH_DIR, "..", "hermes", "data", "industry_map.json")
OUT = os.path.join(CFG.RESEARCH_DIR, "handover", "industry_relative_strength.json")


def _load_map():
    raw = json.load(open(MAP, encoding="utf-8"))
    # 字段: code="sh.600000"、"symbol"=、industry
    out = {}
    for item in raw:
        sym = item.get("symbol") or ""
        code = str(item.get("code") or "")
        ind = item.get("industry") or "UNKNOWN"
        # 统一为 6 位 .SZ / .SH 后缀 (同 tencent cache: '000001_SZ')
        sym6 = sym.split(".")[0] if sym else code.split(".")[-1].zfill(6)
        if sym6:
            out[sym6] = ind
    return out


def _load_day(fp):
    if not os.path.exists(fp):
        return None
    try:
        raw = json.load(open(fp, encoding="utf-8"))
        if not isinstance(raw, list) or len(raw) < 30:
            return None
        return raw
    except Exception:
        return None


def _ret(bars, n):
    if len(bars) < n + 1:
        return None
    return (bars[-1]["c"] / bars[-1 - n]["c"] - 1) * 100


def index_return(etf_file, n):
    """指数近 n 天累计回报(%)。"""
    p = os.path.join(ETF, etf_file)
    d = _load_day(p)
    if not d:
        return None
    return _ret(d, n)


def industry_rs(sym2ind, mkt20, mkt60, limit=4663):
    """行业内个股 20/60 日回报中位数 - 上证对应窗口。返回 per-industry stat。"""
    agg = defaultdict(list)
    for i, (sym, ind) in enumerate(list(sym2ind.items())[:limit]):
        # tencent 命名: {sym}_daily_800.json
        fp = os.path.join(KT, f"{sym}_daily_800.json")
        if not os.path.exists(fp):
            fp = os.path.join(KT, f"{sym}_SZ_daily_800.json")
        if not os.path.exists(fp):
            fp = os.path.join(KT, f"{sym}_SH_daily_800.json")
        d = _load_day(fp)
        if not d:
            continue
        r20 = _ret(d, 20)
        r60 = _ret(d, 60)
        if r20 is not None:
            agg[ind].append((r20, r60))
    out = []
    for ind, lst in agg.items():
        if len(lst) < 5:
            continue  # 样本太少, 均数不稳
        p20 = sorted(x[0] for x in lst)
        p60 = sorted(x[1] for x in lst if x[1] is not None)
        med20 = statistics.median(p20)
        med60 = statistics.median(p60) if p60 else None
        rs20 = round(med20 - (mkt20 or 0), 2)
        rs60 = round(med60 - (mkt60 or 0), 2) if med60 is not None else None
        # RS 排名: 越高越领先市场
        out.append({"industry": ind, "n": len(lst), "med20": round(med20, 2),
                    "rs20": rs20, "med60": round(med60, 2) if med60 is not None else None,
                    "rs60": rs60})
    out.sort(key=lambda x: (x["rs60"] or -1e9, x["rs20"]), reverse=True)
    return out


def main():
    print("读出 market baseline(000001_SH 20/60 日回报)...")
    m20 = index_return("000001_SH_day.json", 20)
    m60 = index_return("000001_SH_day.json", 60)
    if m20 is None or m60 is None:
        print("沪深指数缺数据, exit")
        return
    print(f"  上证 20日 {m20:.2f}% / 60日 {m60:.2f}%")
    sym2ind = _load_map()
    print(f"  行业映射 {len(sym2ind)} 股票")
    inds = industry_rs(sym2ind, m20, m60)
    print(f"  覆盖行业数 {len(inds)}")
    # 简要打印前/后 10
    print("\n== 最强 10 行业(RS20)==")
    for x in inds[:10]:
        print(f"  {x['industry']:20s} n={x['n']:4d} rs20={x['rs20']:+.2f}% rs60={x['rs60']:+.2f}%" if x["rs60"] is not None else
              f"  {x['industry']:20s} n={x['n']:4d} rs20={x['rs20']:+.2f}% rs60=N/A")
    print("\n== 最弱 10 行业 ==")
    for x in inds[-10:]:
        print(f"  {x['industry']:20s} n={x['n']:4d} rs20={x['rs20']:+.2f}% rs60={x['rs60']:+.2f}%")
    payload = {
        "asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        "baseline": {"m20": m20, "m60": m60},
        "coverage": {"stocks_mapped": len(sym2ind), "industries_covered": len(inds)},
        "industries": inds,
    }
    json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()

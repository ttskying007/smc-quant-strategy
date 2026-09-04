# -*- coding: utf-8 -*-
"""Current-market scanner for the combined strategy (SMC TP2-R20 + insider events).
Scans latest klines for live candidates:
A) SMC three-TF signal with TP2-R20 conditions (entry eligible next open)
B) Recent insider events (增持/回购) in last 5 trading days -> event candidates
FIX(2026-08-19): freshness gate — only symbols whose kline latest == market latest
produce candidates (no stale-signal risk); key stocks (holdings + recent events)
are force-refreshed from Sina before scanning when --refresh is passed.
Output: candidate list with signal details, all research-only (no BUY)."""
import io, json, os, sys, subprocess
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we
import config as CFG  # 审计 P1: 统一路径/解释器

KT = CFG.KT_CACHE
OUT = CFG.RESEARCH_DIR
ANNOUNCE_DB = CFG.ANNOUNCE_DB
PY = CFG.PY_PRODUCTION
os.makedirs(OUT, exist_ok=True)


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        o, h, l, c = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c"))
        v = we.f(r.get("v"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    out.sort(key=lambda b: b["t"])
    return out


def market_latest():
    """Determine latest trading date from Sina realtime (authoritative).
    FIX(2026-09-04, P1): 旧实现请求了 Sina 却丢弃结果、硬编码兜底 20260819。
    现在解析 hq_str 第 31 个字段（日期）作为权威最新交易日；失败再回退本地缓存。"""
    import urllib.request
    UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}
    try:
        req = urllib.request.Request("https://hq.sinajs.cn/list=sh600519", headers=UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            b = r.read().decode("gbk", errors="replace")
        # hq_str_sh600519="贵州茅台,open,prevclose,current,high,low,...,date,time,..."
        # 第 31 个字段（index 30）为日期 YYYY-MM-DD（部分源无日期，则用最后 4 字段时间推断）
        m = b.split('"')[1] if '"' in b else ""
        parts = m.split(",")
        if len(parts) > 30 and len(parts[30]) == 10 and parts[30][:4].isdigit():
            date = parts[30].replace("-", "")
            print(f"市场最新交易日(Sina 权威): {date}", flush=True)
            return date
        # 若 Sina 无日期字段，取行情时间字段（第 31 位 YYYY-MM-DD HH:MM:SS 的前半）
        if len(parts) > 31 and len(parts[31]) >= 10:
            date = parts[31][:10].replace("-", "")
            if date[:4].isdigit():
                print(f"市场最新交易日(Sina 时间字段): {date}", flush=True)
                return date
    except Exception as e:
        print(f"Sina 最新交易日获取失败，回退本地缓存: {e}", flush=True)
    # fallback: latest date across kline files that are fresh (from Sina refresh)
    latest = ""
    for f in os.listdir(KT):
        if not f.endswith("_daily_800.json"):
            continue
        bs = bars(os.path.join(KT, f))
        if bs and bs[-1]["t"] > latest:
            latest = bs[-1]["t"]
    if latest:
        print(f"市场最新交易日(本地缓存回退): {latest}", flush=True)
        return latest
    # 最后一个兜底：取当前日期（周一~五），避免 20260819 这种过期硬编码
    import datetime
    _today = datetime.date.today()
    while _today.weekday() >= 5:  # 周末回退到周五
        _today -= datetime.timedelta(days=1)
    print(f"市场最新交易日(日期兜底): {_today.strftime('%Y%m%d')}", flush=True)
    return _today.strftime("%Y%m%d")


def refresh_key_stocks():
    """Force-refresh holdings + recent-event stocks from Sina (small set, fast serial)."""
    try:
        subprocess.run([PY, r"E:\test\smc_project\wdh\refresh_holdings_sina.py"], timeout=1200, capture_output=True)
    except Exception as e:
        print(f"关键股刷新失败(继续): {e}", flush=True)


# A) SMC candidates: seeds whose entry_date == next trading day after last bar (i.e., signal just completed)
import concurrent.futures

def scan_one(p, latest):
    if not p.endswith("_daily_800.json"):
        return None, None
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        return None, None
    # freshness gate: last bar must equal market latest trading date (no stale signals)
    if daily[-1]["t"] != latest:
        return None, None
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    seeds = we.build_seeds(sym, daily)
    last = daily[-1]["t"]
    out = []
    for sd in seeds:
        if int(sd["entry_idx"]) != len(daily) - 1:
            continue
        r20 = sd.get("r20")
        if r20 == "" or r20 is None or not (0 <= float(r20) < 0.15):
            continue
        # v17 SMC leg filters: behavior stage UPTREND/MARKUP + bearish FVG
        entry_idx = int(sd["entry_idx"])
        if entry_idx < 61:
            continue
        # FIX(2026-09-04, 策略层): 旧实现用 ret60>0 代理阶段（注释自认缺量能检查），
        # 与回测口径 stage_and_deep 不一致。现直接复用 paper_sim.stage_and_deep（含量能 vt 判断）。
        import paper_sim as _ps
        _stage, _deep = _ps.stage_and_deep(daily, entry_idx)
        if _stage not in ("UPTREND", "MARKUP"):
            continue
        has_fvg = any(daily[k]["h"] < daily[k - 2]["l"] for k in range(max(3, entry_idx - 12), entry_idx))
        if not has_fvg:
            continue
        fvg_cnt = sum(1 for k in range(max(3, entry_idx - 12), entry_idx) if daily[k]["h"] < daily[k - 2]["l"])
        out.append({"symbol": sym, "event_date": sd["event_date"], "entry_date": sd["entry_date"],
                    "zone_low": sd["zone_low"], "zone_high": sd["zone_high"],
                    "entry_price": sd["entry_price"], "target": sd["target"],
                    "w_permission": sd["w_permission"], "r20": r20, "last": last,
                    "stage": _stage, "bear_fvg": True, "fvg_cnt": fvg_cnt})
    return (out if out else None), last

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="扫描前刷新关键股票（持仓+事件）")
    args = ap.parse_args()
    if args.refresh:
        print("刷新关键股票（持仓+近期事件）...", flush=True)
        refresh_key_stocks()
    latest = market_latest()
    print(f"市场最新交易日: {latest}", flush=True)
    files = [f for f in os.listdir(KT) if f.endswith("_daily_800.json")]
    smc_cands = []
    fresh_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for cands, last in ex.map(lambda p: scan_one(p, latest), files):
            if cands:
                smc_cands.extend(cands)
            if last == latest:
                fresh_count += 1
    print(f"scanned {len(files)} files, fresh={fresh_count} (数据最新), stale skipped (不产生信号)")
    print(f"\n=== A) SMC 三周期信号候选（entry 即将触发）: {len(smc_cands)} ===")
    for c in smc_cands[:15]:
        print(f"  {c['symbol']}: event={c['event_date']} entry={c['entry_date']} zone=[{c['zone_low']},{c['zone_high']}] entry_price={c['entry_price']} target={c['target']} r20={float(c['r20'])*100:.1f}% W={c['w_permission']}")

    # B) recent insider events: query announce DB for last 5 trading days
    import sqlite3
    conn = sqlite3.connect(ANNOUNCE_DB)
    cur = conn.cursor()
    rep = None
    for f in os.listdir(KT):
        if f.endswith("_daily_800.json"):
            rep = bars(os.path.join(KT, f))
            break
    all_dates = sorted(b["t"] for b in rep) if rep else []
    last5 = all_dates[-5:]
    print(f"\n=== B) 最近 5 个交易日: {last5} ===")
    # FIX(2026-09-04, 策略层): LIKE '%增持%' 会命中"终止增持""增持完毕"等噪声；
    # 排除含 终止/完毕/解除/计划(仅计划未实施)/调整 等否定词的标题；去掉 LIMIT 10 截断。
    _neg = ("终止", "完毕", "解除", "取消", "结束", "调整", "变更", "进展", "补充协议", "届满", "减持")
    for d in last5:
        dd = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        cur.execute("SELECT stock_code, stock_name, title FROM announce WHERE date=? AND (title LIKE '%增持%' OR title LIKE '%回购%')", (dd,))
        rows = cur.fetchall()
        rows = [r for r in rows if not any(n in str(r[2]) for n in _neg)]
        print(f"  {dd}: {len(rows)} 增持/回购事件（已滤除终止/完毕等噪声）")
        for code, name, title in rows[:5]:
            print(f"    {code} {name}: {str(title)[:50]}")
    conn.close()

    # save
    with open(os.path.join(OUT, "current_scanner_result.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "latest_date": latest,
            "fresh_count": fresh_count,
            "stale_count": len(files) - fresh_count,
            "coverage_pct": round(100 * fresh_count / len(files), 1) if files else 0,
            "smc_candidates": smc_cands,
            "note": "research-only, no BUY; freshness gate: only latest-data signals; stale=数据未更新到最新（继续后台刷新中）"
        }, fh, ensure_ascii=False, indent=2)
    print("\nscanner result saved (freshness gate)")

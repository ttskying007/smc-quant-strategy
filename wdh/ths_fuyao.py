# -*- coding: utf-8 -*-
"""同花顺金融数据 API 接入（ths_fuyao.py）
- 历史 K 线（prices/historical）→ kline_cache_tencent 兼容格式（数据源冗余）
- 龙虎榜（dragon-tiger-list）→ 大资金追踪增强
- 快照（prices/snapshot）→ 实时价备用
用法：python ths_fuyao.py --kline 600519,000001 | --dragon | --snapshot 600519,000001"""
import io, json, os, sys, time, urllib.request

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API_KEY = "sk-fuyao-OD-fAIzhM7_ir7qWoGUqT18HR_0bQz9S"
BASE = "https://fuyao.aicubes.cn"
CACHE = r"E:\test\smc_project\hermes\kline_cache_tencent"


def call(path, params=""):
    url = f"{BASE}{path}?{params}" if params else f"{BASE}{path}"
    req = urllib.request.Request(url, headers={"X-api-key": API_KEY, "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def fetch_historical_kline(thscode, days=200):
    """拉取历史日 K（thscode 带后缀 600519.SH）—— interval=1d + start/end 毫秒时间戳"""
    import datetime
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days * 86400 * 1000 * 2  # 覆盖 days 个交易日（含周末）
    d = call("/api/a-share/prices/historical", f"thscode={thscode}&interval=1d&start={start_ms}&end={end_ms}&adjust=forward")
    if d.get("code") != 0:
        return None
    item = (d.get("data") or {}).get("item") or []
    bars = []
    if isinstance(item, list):
        for it in item:
            dm = it.get("date_ms")
            t = time.strftime("%Y%m%d", time.localtime(dm / 1000)) if dm else ""
            if t and it.get("open_price") is not None:
                bars.append({"t": t, "o": float(it["open_price"]), "h": float(it["high_price"]),
                             "l": float(it["low_price"]), "c": float(it["close_price"]),
                             "v": float(it.get("volume") or 0)})
    bars.sort(key=lambda b: b["t"])
    return bars


def save_cache(code, bars):
    path = os.path.join(CACHE, f"{code}_daily_800.json")
    existing = []
    if os.path.exists(path):
        try:
            existing = json.load(open(path, encoding="utf-8"))
        except Exception:
            existing = []
    seen = {b["t"] for b in bars}
    merged = [b for b in existing if b["t"] not in seen] + bars
    merged.sort(key=lambda b: b["t"])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, ensure_ascii=False)
    return len(merged)


def fetch_dragon_tiger():
    """龙虎榜（大资金追踪）—— 保存到 research/dragon_tiger.json"""
    d = call("/api/a-share/special-data/dragon-tiger-list", "board_type=all")
    if d.get("code") != 0:
        return None
    data = d.get("data") or {}
    out = {"trade_date": data.get("trade_date"), "count": data.get("count"),
           "items": (data.get("stock_items") or [])[:50]}
    path = r"E:\test\smc_project\research\dragon_tiger.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--kline", help="逗号分隔代码（无后缀，自动补）")
    ap.add_argument("--dragon", action="store_true")
    ap.add_argument("--snapshot", help="逗号分隔代码")
    args = ap.parse_args()

    def to_ths(code):
        return code + (".SH" if code.startswith("6") else ".SZ")

    if args.kline:
        t0 = time.time()
        ok = fail = 0
        for code in [c.strip() for c in args.kline.split(",") if c.strip()]:
            try:
                bars = fetch_historical_kline(to_ths(code), days=200)
                if bars:
                    n = save_cache(code, bars)
                    ok += 1
                else:
                    fail += 1
            except Exception:
                fail += 1
            time.sleep(0.3)
        print(f"同花顺 K 线: OK={ok} FAIL={fail} ({time.time()-t0:.0f}s)")

    if args.dragon:
        dt = fetch_dragon_tiger()
        if dt:
            print(f"龙虎榜: {dt['trade_date']} {dt['count']} 条 → dragon_tiger.json")
            for it in dt["items"][:5]:
                print(f"  {it.get('thscode')} {it.get('name')}")

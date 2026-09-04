# -*- coding: utf-8 -*-
"""同花顺备用数据源（fetch_ths.py）—— 腾讯失败时用同花顺刷新 K 线
增加数据源冗余（P1-3）：腾讯/东财/新浪/网易 + 同花顺"""
import io, json, os, sys, time, urllib.request

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ths_kline import fetch_ths_kline, parse_ths_kline

CACHE = r"E:\test\smc_project\hermes\kline_cache_tencent"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "http://www.10jqka.com.cn/"}


def save_cache(code, bars):
    """写入 kline_cache_tencent 兼容格式（追加/覆盖）"""
    path = os.path.join(CACHE, f"{code}_daily_800.json")
    # merge with existing if present
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


def refresh_symbols(codes, sleep=0.5):
    ok = fail = 0
    for code in codes:
        try:
            data = fetch_ths_kline(code)
            if data:
                bars = parse_ths_kline(data)
                if bars:
                    n = save_cache(code, bars)
                    ok += 1
                else:
                    fail += 1
            else:
                fail += 1
        except Exception as e:
            fail += 1
        time.sleep(sleep)
    return ok, fail


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", help="逗号分隔代码（无后缀）")
    ap.add_argument("--file", help="代码文件（每行一个）")
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    codes = []
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    elif args.file:
        with open(args.file) as fh:
            codes = [l.strip() for l in fh if l.strip()][:args.limit]
    if not codes:
        # 默认测试 5 只
        codes = ["000001", "600519", "300750", "002594", "601318"]
    t0 = time.time()
    ok, fail = refresh_symbols(codes)
    print(f"同花顺刷新: OK={ok} FAIL={fail} ({time.time()-t0:.0f}s)")

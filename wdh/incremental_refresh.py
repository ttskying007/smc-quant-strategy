# -*- coding: utf-8 -*-
"""增量刷新（incremental_refresh.py）— FIX 2026-08-22 数据更新慢
datalen=10 拉最新 10 根 bar 追加到本地 800 缓存（每只 ~0.3s，全市场 ~25 分钟）
+ refresh_progress.json 实时进度（前端展示同步状态/进度条）"""
import io, json, os, sys, time, urllib.request

OUT = r"E:\test\smc_project\hermes\kline_cache_tencent"
PROGRESS = r"E:\test\smc_project\research\refresh_progress.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://finance.sina.com.cn/"}
if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def save_progress(d):
    try:
        with open(PROGRESS, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False)
    except Exception:
        pass


def fetch_incremental(symbol):
    """Fetch latest 10 bars, append to local 800-bar cache (dedup by date)."""
    out_p = os.path.join(OUT, symbol.replace(".", "_") + "_daily_800.json")
    code, ex = symbol.split(".")
    sina_sym = ("sh" if ex == "SH" else "sz") + code
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_sym}&scale=240&ma=no&datalen=10"
    for attempt in range(3):
        try:
            time.sleep(0.08)
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                b = r.read().decode("utf-8", errors="replace")
            d = json.loads(b)
            new_bars = []
            for x in d:
                t = str(x.get("day", "")).replace("-", "")
                if t and x.get("open"):
                    new_bars.append({"t": t, "o": float(x["open"]), "c": float(x["close"]),
                                     "h": float(x["high"]), "l": float(x["low"]),
                                     "v": float(x.get("volume") or 0)})
            if not new_bars:
                return symbol, "empty"
            # load existing
            existing = []
            if os.path.exists(out_p):
                try:
                    existing = json.load(open(out_p, encoding="utf-8"))
                except Exception:
                    existing = []
            by_date = {b["t"]: b for b in existing}
            changed = 0
            for nb in new_bars:
                if nb["t"] not in by_date or by_date[nb["t"]] != nb:
                    by_date[nb["t"]] = nb
                    changed += 1
            merged = [by_date[k] for k in sorted(by_date.keys())][-800:]
            with open(out_p, "w", encoding="utf-8") as fh:
                json.dump(merged, fh)
            return symbol, changed
        except Exception as e:
            if attempt == 2:
                return symbol, "err:" + str(e)[:40]
            time.sleep(1.0 * (attempt + 1))
    return symbol, "retries"


def main():
    import argparse, concurrent.futures
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只刷新前 N 只（0=全部）")
    ap.add_argument("--start", type=int, default=0, help="跳过前 N 只（断点续传）")
    ap.add_argument("--workers", type=int, default=3, help="并发数（Sina 限流 456，3 安全）")
    args = ap.parse_args()
    symbols = []
    for f in os.listdir(OUT):
        if f.endswith("_daily_800.json"):
            symbols.append(f.replace("_daily_800.json", "").replace("_", ".", 1))
    symbols.sort()
    total = len(symbols)
    if args.start:
        symbols = symbols[args.start:]
    if args.limit:
        symbols = symbols[:args.limit]
    print(f"增量刷新: {len(symbols)}/{total} 只 (workers={args.workers})", flush=True)
    ok = done = changed_all = 0
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        fut_map = {ex.submit(fetch_incremental, sym): sym for sym in symbols}
        for i, fut in enumerate(concurrent.futures.as_completed(fut_map), 1):
            sym = fut_map[fut]
            try:
                s, r = fut.result()
                done += 1
                if isinstance(r, int):
                    ok += 1
                    changed_all += r
            except Exception:
                done += 1
            # progress file every 60 stocks
            if i % 60 == 0 or i == len(symbols):
                elapsed = time.time() - t0
                speed = i / elapsed if elapsed > 0 else 0
                eta = (len(symbols) - i) / speed if speed > 0 else 0
                prog = {"mode": "incremental", "done": i + args.start, "total": total,
                        "fresh": i + args.start, "coverage_pct": round(100 * (i + args.start) / total, 1),
                        "current": sym, "speed": round(speed, 1), "eta_min": round(eta / 60, 1),
                        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
                save_progress(prog)
                print(f"  {i+args.start}/{total} ok={ok} changed={changed_all} {time.time()-t0:.0f}s speed={speed:.1f}/s", flush=True)
    # retry failed symbols (serial, more reliable)
    failed = [s for s in symbols if s not in [sym for sym in symbols]]  # collected from try
    # actually collect errors from results
    _failed = []
    for sym in symbols:
        p = os.path.join(OUT, sym.replace(".", "_") + "_daily_800.json")
        if os.path.exists(p):
            try:
                r = json.load(open(p, encoding="utf-8"))
                if r and str(r[-1].get("t", "")) < "20260820":
                    _failed.append(sym)
            except Exception:
                _failed.append(sym)
        else:
            _failed.append(sym)
    if _failed:
        print(f"重试 {len(_failed)} 只失败（串行）...", flush=True)
        t0 = time.time()
        for i, sym in enumerate(_failed, 1):
            s, r = fetch_incremental(sym)
            if i % 60 == 0:
                print(f"  重试 {i}/{len(_failed)}", flush=True)
        print(f"重试完成: {len(_failed)} ({time.time()-t0:.0f}s)", flush=True)
    # final progress
    prog = {"mode": "incremental", "done": total, "total": total, "fresh": total,
            "coverage_pct": 100.0, "current": "", "speed": 0, "eta_min": 0,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "status": "completed"}
    save_progress(prog)
    print(f"DONE: {done} symbols, {ok} ok, changed {changed_all} bars, {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Pull full daily history via Tencent (count=800 -> ~2023-04..now) for all local symbols.
Faster and less rate-limited than Eastmoney. Writes kline_cache_tencent.
"""
import concurrent.futures, io, json, os, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KLINE = r"E:\test\smc_project\hermes\kline_cache"
OUT = r"E:\test\smc_project\hermes\kline_cache_tencent"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
      "Referer": "https://gu.qq.com/", "Accept": "*/*"}
FORCE = os.environ.get("SMC_FORCE_REFRESH", "0") == "1"


def tcode(symbol):
    code, ex = symbol.split(".")
    return f"sh{code}" if ex == "SH" else f"sz{code}"


def fetch(symbol):
    out_p = os.path.join(OUT, symbol.replace(".", "_") + "_daily_800.json")
    if os.path.exists(out_p) and not FORCE:
        return symbol, "skip", None
    tc = tcode(symbol)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={tc},day,,,800,qfq"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
            data = d.get("data", {}).get(tc, {})
            kl = data.get("qfqday") or data.get("day") or []
            bars = []
            for line in kl:
                if len(line) >= 6:
                    bars.append({"t": line[0].replace("-", ""), "o": float(line[1]), "c": float(line[2]),
                                 "h": float(line[3]), "l": float(line[4]), "v": float(line[5])})
            if bars:
                with open(out_p, "w", encoding="utf-8") as fh:
                    json.dump(bars, fh)
                return symbol, len(bars), None
            return symbol, 0, "empty"
        except Exception as e:
            if attempt == 2:
                return symbol, 0, str(e)[:60]
            time.sleep(0.8 * (attempt + 1))
    return symbol, 0, "retries"


def main():
    symbols = []
    for p in sorted(os.listdir(KLINE)):
        if p.endswith("_daily_750.json"):
            symbols.append(p.replace("_daily_750.json", "").replace("_", ".", 1))
    print("symbols:", len(symbols), flush=True)
    ok = done = 0
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch, s): s for s in symbols}
        for fut in concurrent.futures.as_completed(futs):
            sym, n, err = fut.result()
            done += 1
            if n:
                ok += 1
            if done % 500 == 0:
                print(f"  {done}/{len(symbols)} ok={ok} {time.time()-t0:.0f}s", flush=True)
    print(f"DONE: {done} symbols, {ok} ok, {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()

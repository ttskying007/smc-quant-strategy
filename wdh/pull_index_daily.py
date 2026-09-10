# -*- coding: utf-8 -*-
"""pull_index_daily.py —— 指数/ETF 日线刷新(E-score F2/F3 数据源, V4 D1)
腾讯源拉: 上证指数(sh000001) + 中证1000ETF(sh512100) + 中证500ETF(sh510500)。
写入 kline_cache_etf/{SH,SZ}_{code}_daily.json(SH_000001_daily.json 等, 与现有命名族一致)。
增量: 文件存在 → 只在末尾追加缺失日期; 全量环境变量 SMC_FORCE_REFRESH=1。
调度: daily_combo_run 尾部(在 escore_daily 之前)。"""
import io, json, os, sys, time, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUT = r"E:\test\smc_project\hermes\kline_cache_etf"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
      "Referer": "https://gu.qq.com/", "Accept": "*/*"}
FORCE = os.environ.get("SMC_FORCE_REFRESH", "0") == "1"
TARGETS = [("sh000001", "SH_000001_daily.json"),      # 上证指数(F3)
           ("sh512100", "SH_512100_daily.json"),      # 中证1000ETF(F2 首选)
           ("sh510500", "SH_510500_daily.json")]      # 中证500ETF(备用)


def fetch_full(tc):
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
                    bars.append({"t": line[0].replace("-", ""), "o": float(line[1]),
                                 "c": float(line[2]), "h": float(line[3]),
                                 "l": float(line[4]), "v": float(line[5])})
            return bars
        except Exception:
            if attempt == 2:
                return []
            time.sleep(0.8 * (attempt + 1))
    return []


def norm_bars(bars):
    """规范为 (t8, c) 升序去重 —— 与 core.escore 兼容。"""
    seen = {}
    for b in bars:
        t = str(b.get("t") or "")[:10].replace("-", "")
        if len(t) == 8:
            seen[t] = float(b["c"])
    return [(t, seen[t]) for t in sorted(seen)]


for tc, fname in TARGETS:
    fp = os.path.join(OUT, fname)
    bars = fetch_full(tc)
    if not bars:
        print(f"  {fname}: 拉取失败(保留旧文件)")
        continue
    new = norm_bars(bars)
    if os.path.exists(fp) and not FORCE:
        try:
            old = norm_bars(json.load(open(fp, encoding="utf-8")))
        except Exception:
            old = []
        merged = {t: c for t, c in old}
        merged.update({t: c for t, c in new})
        final = [(t, merged[t]) for t in sorted(merged)]
    else:
        final = new
    json.dump([{"t": t, "c": c} for t, c in final], open(fp, "w", encoding="utf-8"))
    print(f"  {fname}: {len(final)} 根 (新 {len(new)}) asof={final[-1][0] if final else '-'}")
print("指数刷新完成")
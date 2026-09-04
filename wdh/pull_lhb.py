# -*- coding: utf-8 -*-
"""龙虎榜历史拉取（大资金直接痕迹）：2024-01 起按日期分页"""
import io, json, os, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = r"E:\test\smc_project\hermes\lhb_cache"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://data.eastmoney.com/"}


def fetch_day(date):
    """Fetch LHB detail for one trade date."""
    url = (f"https://datacenter-web.eastmoney.com/api/data/v1/get?"
           f"sortColumns=SECURITY_CODE&sortTypes=1&pageSize=500&pageNumber=1"
           f"&reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL"
           f"&filter=(TRADE_DATE%3D%27{date}%27)")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    result = d.get("result") or {}
    return result.get("data") or []


def main():
    # pull last 10 trading days (sample for signal test)
    dates = ["2026-08-19", "2026-08-18", "2026-08-17", "2026-08-14", "2026-08-13",
             "2026-08-12", "2026-08-11", "2026-08-10", "2026-08-07", "2026-08-06"]
    total = 0
    for dt in dates:
        try:
            rows = fetch_day(dt)
            if rows:
                with open(os.path.join(OUT, dt.replace("-", "") + ".json"), "w", encoding="utf-8") as fh:
                    json.dump(rows, fh, ensure_ascii=False)
                total += len(rows)
                print(f"  {dt}: {len(rows)} 条", flush=True)
        except Exception as e:
            print(f"  {dt}: FAIL {str(e)[:50]}", flush=True)
        time.sleep(1.5)
    print(f"DONE: {total} 条龙虎榜", flush=True)


if __name__ == "__main__":
    main()

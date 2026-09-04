# -*- coding: utf-8 -*-
"""分批全市场刷新（incremental_batch_refresh.py）
每日后台刷一批（默认600只），增量感知：只刷新 last-date < 最新 的文件。
多日完成全市场一轮。配合 scanner 新鲜度门控（数据旧不产生信号）。
用法：python incremental_batch_refresh.py [--batch 600] [--workers 2]"""
import concurrent.futures, io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\wdh")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pull_sina_daily as ps

OUT = ps.OUT


def stale_files(latest):
    """Files whose last bar date < latest trading date (need refresh)."""
    stale = []
    for f in os.listdir(OUT):
        if not f.endswith("_daily_800.json"):
            continue
        p = os.path.join(OUT, f)
        try:
            raw = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if raw and raw[-1].get("t", "") < latest:
            stale.append(f.replace("_daily_800.json", "").replace("_", ".", 1))
    return stale


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=600)
    args = ap.parse_args()
    # latest trading date: max across files already fresh (from holdings refresh)
    latest = ""
    for f in os.listdir(OUT):
        if not f.endswith("_daily_800.json"):
            continue
        try:
            raw = json.load(open(os.path.join(OUT, f), encoding="utf-8"))
            if raw and raw[-1].get("t", "") > latest:
                latest = raw[-1].get("t", "")
        except Exception:
            pass
    if not latest:
        print("无法确定最新交易日", flush=True)
        return
    stale = stale_files(latest)
    print(f"最新交易日: {latest} | stale 待刷新: {len(stale)} | 本批: {args.batch}", flush=True)
    batch = stale[:args.batch]
    t0 = time.time()
    ok = 0
    skip = 0
    ps.FORCE = True  # force overwrite stale files (module attr, not env) 
    # serial (Sina rate-limits concurrency)
    for i, sym in enumerate(batch):
        s, n, err = ps.fetch(sym)
        if isinstance(n, int) and n > 0:
            ok += 1
        elif n == "skip":
            skip += 1
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(batch)} ok={ok} skip={skip} {time.time()-t0:.0f}s", flush=True)
    print(f"BATCH DONE: {ok}/{len(batch)} refreshed, {skip} skip in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()

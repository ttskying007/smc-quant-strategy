# -*- coding: utf-8 -*-
"""pull_tencent_incremental.py v2 —— 日线增量(kline 端点, append 模式, 跳变守卫)
fqkline 端点 501(2026-09-12 风控/停用) → 改 kline/kline(不复权)。
安全设计:
  ① append 模式: 不覆盖历史前复权 bars, 只把【新增日期】append 到尾部
  ② 跳变守卫: 新 bar 开盘 vs 缓存末bar 收盘跳变 >11%(涨停+费都不到) → 拒绝该文件
     (口径切换/除权检测; 留给 fqkline 恢复后重拉)
  ③ 去重: 已存在日期跳过
调度: daily_combo_run 开头。"""
import argparse, concurrent.futures, glob, io, json, os, sys, time, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
      "Referer": "https://gu.qq.com/", "Accept": "*/*"}

ap = argparse.ArgumentParser()
ap.add_argument("--target", default=time.strftime("%Y%m%d"))
ap.add_argument("--workers", type=int, default=8)
ap.add_argument("--sample", type=int, default=0,
                help="只刷排序后前 N 个待刷新文件(分批; 0=全量)")
args = ap.parse_args()
TARGET = args.target
JUMP_GUARD = 0.11          # 11% 跳变守卫

def tcode_of(fp):
    base = os.path.basename(fp).replace("_daily_800.json", "")
    if "_" in base:
        code, ex = base.split("_")
    else:
        code, ex = base, ("SH" if base.startswith("6") else "SZ")
    return code, ("sh" + code if ex == "SH" else "sz" + code)

def fetch(fp):
    code, tc = tcode_of(fp)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={tc},day,,,320"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
            data = d.get("data", {}).get(tc, {})
            kl = data.get("day") or []
            bars = [{"t": line[0].replace("-", ""), "o": float(line[1]), "c": float(line[2]),
                     "h": float(line[3]), "l": float(line[4]), "v": float(line[5])}
                    for line in kl if len(line) >= 6]
            if not bars:
                return fp, 0, "empty"
            try:
                old = json.load(open(fp, encoding="utf-8"))
            except Exception:
                old = []
            if not old:
                return fp, 0, "no-history"
            last_t = str(old[-1]["t"])[:8]
            # 新增 = 日期 > 缓存末bar
            new = [b for b in bars if str(b["t"])[:8] > last_t]
            if not new:
                return fp, 0, None                    # 已最新
            # 跳变守卫: 首 bar 开盘 vs 缓存末收盘
            prev_c = float(old[-1]["c"])
            gap = abs(new[0]["o"] / prev_c - 1)
            if prev_c > 0 and gap > JUMP_GUARD:
                return fp, 0, f"jump{gap:.0%}"
            merged = old + new
            with open(fp, "w", encoding="utf-8") as fh:
                json.dump(merged[-800:], fh)
            return fp, len(new), None
        except Exception as e:
            if attempt == 2:
                return fp, 0, str(e)[:50]
            time.sleep(0.8 * (attempt + 1))
    return fp, 0, "retries"

stale = []
for fp in sorted(glob.glob(os.path.join(KT, "*_daily_800.json"))):
    try:
        raw = json.load(open(fp, encoding="utf-8"))
        last = str(raw[-1].get("t"))[:8] if raw else ""
    except Exception:
        last = ""
    if not last or last < TARGET:
        stale.append(fp)
print(f"目标 {TARGET} | 待刷新 {len(stale)}/{len(glob.glob(os.path.join(KT, '*_daily_800.json')))}")
if args.sample > 0 and len(stale) > args.sample:
    stale = stale[:args.sample]
    print(f"分批: 本批 {len(stale)}")

ok = jump = fail = n_bar = 0
t0 = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
    futs = {ex.submit(fetch, fp): fp for fp in stale}
    for fut in concurrent.futures.as_completed(futs):
        fp, n, err = fut.result()
        if n:
            ok += 1; n_bar += n
        elif err is None:
            pass                          # 已最新
        elif err and err.startswith("jump"):
            jump += 1
        else:
            fail += 1
        if (ok + jump + fail) % 500 == 0:
            print(f"  {ok + jump + fail}/{len(stale)} ok={ok} jump={jump} {time.time()-t0:.0f}s", flush=True)
print(f"完成: ok={ok}(+{n_bar}bars) jump={jump} fail={fail} {time.time()-t0:.0f}s")
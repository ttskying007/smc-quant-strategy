# -*- coding: utf-8 -*-
"""纸面裁决脚本（paper_adjudicate.py）—— 8/27-9/1 到期平仓 + 与回测对比
用法：数据推进到到期日后运行（python paper_adjudicate.py --date 20260827）
对 58 笔 OPEN 旧持仓用到期日收盘价平仓，记录 pnl，与 v20c/v20d 回测 avg 对比"""
import io, json, os, sys, argparse, datetime
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps

led = ps.load_ledger()
open_old = [t for t in led if t.get("status") == "OPEN"]
print(f"OPEN 旧持仓: {len(open_old)} 笔（8/12-14 信号，15 日到期）\n")

# group by signal date -> expiry
for t in open_old:
    sig = str(t.get("signal_date", "") or t.get("disclose_date", ""))
    try:
        d = datetime.date(int(sig[:4]), int(sig[5:7]), int(sig[8:10]))
        expire = d + datetime.timedelta(days=15)
        t["_expire"] = expire.strftime("%Y%m%d")
    except Exception:
        t["_expire"] = ""


def adjudicate(target_date):
    """Close OPEN positions whose expiry <= target_date at close price."""
    closed = 0
    results = []
    for t in open_old:
        exp = t.get("_expire", "")
        if not exp or exp > target_date:
            continue
        code = t.get("code")
        bs = ps.bars_of(code)
        if not bs:
            continue
        dates = [b["t"] for b in bs]
        if target_date not in dates:
            # use last available bar <= target
            prev = [d for d in dates if d <= target_date]
            if not prev:
                continue
            target_date_actual = prev[-1]
        else:
            target_date_actual = target_date
        i = dates.index(target_date_actual)
        close_px = bs[i]["c"]
        ep = t.get("entry_price") or 0
        if ep <= 0:
            continue
        pnl = round((close_px / ep - 1) * 100 - 0.20, 4)
        t["status"] = "CLOSED"
        t["exit_reason"] = "PAPER_ADJUDICATE"
        t["pnl_pct"] = pnl
        t["exit_date"] = target_date_actual
        t["note"] = (t.get("note", "") + " | 纸面裁决平仓").strip()
        results.append({"code": code, "name": t.get("name"), "ep": ep, "close": close_px, "pnl": pnl})
        closed += 1
    return closed, results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="裁决日期 YYYYMMDD（8/27-9/1）")
    ap.add_argument("--commit", action="store_true", help="确认写入 ledger（默认 dry-run）")
    args = ap.parse_args()
    closed, results = adjudicate(args.date)
    print(f"裁决日 {args.date}: 可平仓 {closed} 笔\n")
    if results:
        pnls = [r["pnl"] for r in results]
        wins = [x for x in pnls if x > 0]
        print(f"  平均: {sum(pnls)/len(pnls):+.2f}% | 胜率: {100*len(wins)/len(pnls):.0f}%")
        print(f"  对比: v20c 事件 avg +6.5% | v20d 事件 avg +7.4%")
        for r in results[:5]:
            print(f"    {r['code']} {r['name']} ep={r['ep']} close={r['close']} pnl={r['pnl']:+.2f}%")
    if args.commit and closed:
        ps.save_ledger(led)
        print(f"\n✅ 已提交 {closed} 笔平仓到 ledger")
    else:
        print(f"\n(dry-run，未写入。确认后加 --commit)")


if __name__ == "__main__":
    main()

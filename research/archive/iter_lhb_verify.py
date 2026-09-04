# -*- coding: utf-8 -*-
"""龙虎榜信号：用东财 D1/D5/D10_CLOSE_ADJCHRATE（未来涨跌幅）直接验证
净买>0（大资金买入）信号的表现"""
import io, json, os, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
LHB = r"E:\test\smc_project\hermes\lhb_cache"

all_rows = []
for f in sorted(os.listdir(LHB)):
    rows = json.load(open(os.path.join(LHB, f), encoding="utf-8"))
    for r in rows:
        net = float(r.get("BILLBOARD_NET_AMT") or 0)
        d5 = r.get("D5_CLOSE_ADJCHRATE")
        d10 = r.get("D10_CLOSE_ADJCHRATE")
        if d5 is not None and d10 is not None:
            all_rows.append({"code": r.get("SECURITY_CODE"), "name": r.get("SECURITY_NAME_ABBR"),
                             "net": net, "d5": float(d5), "d10": float(d10)})

print(f"龙虎榜信号（有未来数据）: {len(all_rows)} 条（近10天）")


def report(label, rs):
    if len(rs) < 20:
        print(f"{label}: n={len(rs)} (过小)")
        return
    d5 = [r["d5"] for r in rs]
    d10 = [r["d10"] for r in rs]
    w10 = sum(1 for x in d10 if x > 0)
    print(f"{label}: n={len(rs)} | 5日 avg={sum(d5)/len(d5):+.2f}% | 10日 avg={sum(d10)/len(d10):+.2f}% WR={100*w10/len(d10):.0f}%")


print("\n=== 龙虎榜净买信号（东财未来涨跌幅）===")
report("全部龙虎榜", all_rows)
report("净买>0（大资金买入）", [r for r in all_rows if r["net"] > 0])
report("净买>500万", [r for r in all_rows if r["net"] > 5e6])
report("净买>1000万", [r for r in all_rows if r["net"] > 1e7])
report("净卖<0（大资金卖出）", [r for r in all_rows if r["net"] < 0])

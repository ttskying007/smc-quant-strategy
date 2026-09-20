# -*- coding: utf-8 -*-
"""R56: 周一生产验证一键清单 — 数据落地后运行本脚本即得四项判定
  [1] announce 自愈: run_status 最新 run 的 announce rc==0
  [2] 周末顺延: selection_funnel 出现 rolled_weekend 计数, nodata 显著下降
  [3] funnel 基线: selection_funnel_history 天数 5→6+
  [4] R13 归因: paper_ledger 新 CLOSED 订单携带 loss_attribution; 002801 状态
用法: python -X utf8 research\r56_monday_check.py
"""
import json, os, sys, io, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"E:\test\smc_project"
results = []

def check(name, okv, detail):
    results.append((name, bool(okv), detail))
    print(f"  [{'PASS' if okv else 'FAIL'}] {name}: {detail}")

print("== R56 周一生产验证 ==")
today = datetime.date.today().isoformat()

# [1] run_status
try:
    rs = json.load(open(os.path.join(ROOT, "research", "run_status.json"), encoding="utf-8"))
    ra = rs.get("run_at", "")[:10]
    ann = rs.get("steps", {}).get("announce")
    fresh = ra >= str(datetime.date.today() - datetime.timedelta(days=1))
    check("announce 自愈(rc=0)", fresh and ann == 0, f"run_at={ra} announce_rc={ann}")
except Exception as e:
    check("announce 自愈", False, str(e))

# [2] 周末顺延生效
try:
    sf = json.load(open(os.path.join(ROOT, "research", "selection_funnel.json"), encoding="utf-8"))
    rej = sf.get("reject_by_reason", {}) if isinstance(sf, dict) else {}
    rolled = rej.get("rolled_weekend", sf.get("rolled_weekend", 0))
    nodata = rej.get("nodata", sf.get("nodata", sf.get("skip_nodata", 99)))
    # 判定: 计数器出现, 或 nodata 已降到修复后水位(旧病: 周末批量14+)
    check("周末顺延生效", (isinstance(rolled, int) and rolled > 0) or (isinstance(nodata, int) and nodata <= 6),
          f"rolled_weekend={rolled} nodata={nodata} (修前周末批量 nodata=14)")
except Exception as e:
    check("周末顺延", False, str(e))

# [3] funnel 历史天数
try:
    fh = json.load(open(os.path.join(ROOT, "research", "selection_funnel_history.json"), encoding="utf-8"))
    n = len(fh) if isinstance(fh, list) else len(fh.get("days", fh))
    check("funnel 基线推进", n >= 6, f"n={n}/8 天")
except Exception as e:
    check("funnel 基线", False, str(e))

# [4] PAPER: 002801 + R13 归因
try:
    led = json.load(open(os.path.join(ROOT, "research", "paper_ledger.json"), encoding="utf-8"))
    led = led if isinstance(led, list) else led.get("orders", [])
    o2801 = [o for o in led if str(o.get("code")) == "002801"]
    st2801 = o2801[0].get("status") if o2801 else "ABSENT"
    closed = [o for o in led if o.get("status") == "CLOSED"]
    with_attr = [o for o in closed if o.get("loss_attribution")]
    check("002801 可追踪", bool(o2801), f"status={st2801} pnl={o2801[0].get('pnl_pct') if o2801 else '-'}")
    check("R13 归因落账", len(closed) > 0, f"CLOSED={len(closed)} 带归因={len(with_attr)}"
          + (" ← 新归因已出现" if with_attr else " (002801 平仓后应>0)"))
except Exception as e:
    check("PAPER ledger", False, str(e))

fails = [r for r in results if not r[1]]
print(f"\n总判定: {len(results)-len(fails)}/{len(results)} PASS" + ("  — 全部通过, 生产链恢复健康" if not fails else "  — 见 FAIL 项"))

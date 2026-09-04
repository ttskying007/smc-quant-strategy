#!/usr/bin/env python3
"""SMC V7 V3 状态汇总报告"""
import json, sys
from pathlib import Path

d = Path("/root/.hermes/smc_opt_v7_v3")
print("="*70)
print("  SMC V7 V3 OPTIMIZATION STATUS REPORT")
print("="*70)

# 最佳参数
bf = d / "v7v3_best.json"
if bf.exists():
    b = json.loads(bf.read_text())
    print(f"\n  📊 最佳参数:")
    print(f"     Score:  {b.get('sc', '?')}")
    print(f"     WR:     {b.get('iw', 0):.0f}% / {b.get('ow', 0):.0f}% (IS/OOS)")
    print(f"     PF:     {b.get('ip', 0):.1f} / {b.get('op', 0):.1f}")
    print(f"     RR:     {b.get('rr', 0):.1f}")
    print(f"     SL/TP:  {b.get('sl', 0):.2f}% / {b.get('tp', 0):.1f}%")
    print(f"     Trades: n={b.get('in', 0)}/{b.get('on', 0)}")

# 历史
hf = d / "v7v3_hist.json"
if hf.exists():
    h = json.loads(hf.read_text())
    if h:
        print(f"\n  📈 迭代历史 ({len(h)} 代):")
        for e in h[:5]:
            print(f"     gen {e.get('g','?'):3d} | SC={e.get('sc',0):.1f} | WR={e.get('iw',0):.0f}/{e.get('ow',0):.0f}% | PF={e.get('ip',0):.1f}/{e.get('op',0):.1f} | n={e.get('in',0)+e.get('on',0)} | RR={e.get('rr',0):.1f}")
        if len(h) > 5:
            print(f"     ...")
            last = h[-1]
            print(f"     gen {last.get('g','?'):3d} | SC={last.get('sc',0):.1f} | WR={last.get('iw',0):.0f}/{last.get('ow',0):.0f}% | PF={last.get('ip',0):.1f}/{last.get('op',0):.1f} | n={last.get('in',0)+last.get('on',0)} | RR={last.get('rr',0):.1f}")
        
        # 是否停滞
        if all(e.get('iw',0) == h[-1].get('iw',0) for e in h[-5:]):
            print(f"\n  ⚠️  停滞检测: 最后{min(len(h),10)}代WR无变化")
        
        # 最高WR
        max_iw = max(e.get('iw',0) for e in h)
        max_ow = max(e.get('ow',0) for e in h)
        print(f"     最高IS WR: {max_iw:.0f}%")
        print(f"     最高OOS WR: {max_ow:.0f}%")
        print(f"     最高RR: {max(e.get('rr',0) for e in h):.1f}")

print("\n" + "="*70)
print("  FILES:")
for f in sorted(d.glob("*")):
    size = f.stat().st_size
    print(f"    {f.name:30s} {size:>6} bytes")
print("="*70)

# V7+历史
v7p = Path("/root/.hermes/smc_opt_v7plus")
if v7p.exists():
    hf2 = v7p / "v7p_history.json"
    if hf2.exists():
        h2 = json.loads(hf2.read_text())
        if h2:
            print(f"\n  V7+ 历史 ({len(h2)} 代):")
            best_e = max(h2, key=lambda x: x.get('is_wr',0))
            print(f"     最高IS WR: {best_e.get('is_wr',0):.0f}% (gen {best_e.get('gen','?')})")
            best_rr = max(h2, key=lambda x: x.get('actual_rr',0))
            print(f"     最高RR: {best_rr.get('actual_rr',0):.1f} (gen {best_rr.get('gen','?')})")
            if h2:
                last = h2[-1]
                print(f"     最后: WR={last.get('is_wr',0):.0f}/{last.get('oos_wr',0):.0f}% RR={last.get('actual_rr',0):.1f} PF={last.get('is_pf',0):.1f}/{last.get('oos_pf',0):.1f}")

# 已停止的旧引擎
print(f"\n  运行中的进程:")
import subprocess
r = subprocess.run(['pgrep','-af','smc_engine'], capture_output=True, text=True, timeout=3)
if r.stdout.strip():
    for line in r.stdout.strip().split('\n'):
        print(f"    {line}")
else:
    print("    (无)")

print(f"\n  Hubble直连: ", end="")
try:
    import urllib.request
    o = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request("http://43.167.234.49:3101/api/v2/cnstock/stocks?symbol=000001.SZ&interval=daily&limit=3",
        headers={"X-API-Key":"123456"})
    with o.open(req, timeout=5) as r:
        d = json.loads(r.read().decode())
        k = d.get('data', [])
        print(f"✅ OK ({len(k)} bars)")
except Exception as e:
    print(f"❌ {e}")

print(f"\n  代理状态: ", end="")
r = subprocess.run(['pgrep','-f','mihomo'], capture_output=True, text=True, timeout=3)
print(f"{'✅ 运行中' if r.stdout.strip() else '❌ 未运行'} PID={r.stdout.strip() if r.stdout.strip() else 'N/A'}")
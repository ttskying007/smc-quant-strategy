# -*- coding: utf-8 -*-
"""r38_rebaseline_verify.py —— 重基线验收: combo_v20f2 vs 证据包 vs 历史归档.

用户批准 R38r 合并重基线后, 本脚本做三向一致性核对:
  ① combo_v20f2_trades.csv (新冻结基线, gen_v20f2_wilder_h12.py 产出)
  ② r38_combo_wilder_h12_trades.csv (R38r 研究证据包 EVENT 腿逐笔)
  ③ archive/combo_v20f_trades_legacy_dx_h15.csv (历史归档, 不得删除)

判据(预注册):
  · ① 的 EVENT 腿逐笔应与 ② 完全一致(同口径同代码路径) → 必须 100% 匹配
  · ① 的组合级指标应落在 R38r 报告的 PF3.72/MDD-448/avg+3.85 附近
  · ③ 保留完整(n=1974), 仅作历史对照, 不参与新基线判定
纯校验, 不修改任何数据文件。
"""
import csv, io, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
P_NEW = os.path.join(HERE, "combo_v20f2_trades.csv")
P_EVID = os.path.join(HERE, "r38_combo_wilder_h12_trades.csv")
P_ARCH = os.path.join(HERE, "archive", "combo_v20f_trades_legacy_dx_h15.csv")

for p in (P_NEW, P_EVID, P_ARCH):
    print("exists %-58s %s" % (os.path.basename(p), os.path.exists(p)))

def load(p):
    if not os.path.exists(p):
        return []
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))

def f(x, d=0.0):
    try: return float(x)
    except: return d

def mat(rows):
    if not rows:
        return None
    p = [f(r["net_pnl_pct"]) for r in rows]
    w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    eq = 0.0; peak = 0.0; mdd = 0.0
    for x in p:
        eq += x; peak = max(peak, eq); mdd = min(mdd, eq - peak)
    sp = sorted(p)
    return dict(n=len(p), wr=100*len(w)/len(p), avg=sum(p)/len(p),
                med=sp[len(sp)//2], pf=pf, mdd=mdd, sum=sum(p))

new_all = load(P_NEW)
new_ev = [r for r in new_all if r.get("src") == "EVENT"]
new_cont = [r for r in new_all if r.get("src") == "CONT"]
evid = load(P_EVID)
arch = load(P_ARCH)

print("\n" + "="*96)
print("① 新冻结基线 combo_v20f2_trades.csv")
print("="*96)
sn = mat(new_all)
print("  组合: n=%d 胜率=%.1f%% avg=%+.2f%% 中位=%+.2f%% PF=%.2f MDD=%.0f 累计=%+.0f%%"
      % (sn["n"], sn["wr"], sn["avg"], sn["med"], sn["pf"], sn["mdd"], sn["sum"]))
print("  分解: EVENT n=%d | CONT n=%d" % (len(new_ev), len(new_cont)))
print("  参照(R38r 证据包): 组合 PF≈3.72 / MDD≈-448 / avg≈+3.85%")

print("\n" + "="*96)
print("② 逐笔一致性: 新基线 EVENT vs R38r 证据包 (必须完全一致)")
print("="*96)
def key(r):
    return (str(r.get("symbol")), str(r.get("entry_date")))

m_new = {key(r): r for r in new_ev}
m_ev = {key(r): r for r in evid}
only_new = set(m_new) - set(m_ev)
only_ev = set(m_ev) - set(m_new)
common = set(m_new) & set(m_ev)
print("  新基线 EVENT=%d | 证据包=%d | 交集=%d" % (len(m_new), len(m_ev), len(common)))
print("  仅新基线有: %d | 仅证据包有: %d" % (len(only_new), len(only_ev)))

mismatch = []
for k in sorted(common):
    a = f(m_new[k]["net_pnl_pct"]); b = f(m_ev[k]["net_pnl_pct"])
    if abs(a - b) > 1e-6:
        mismatch.append((k, a, b))
print("  net_pnl_pct 不一致: %d" % len(mismatch))
for k, a, b in mismatch[:8]:
    print("    %s: 新=%+.4f 证据=%+.4f" % (k, a, b))

if not only_new and not only_ev and not mismatch:
    print("\n  ✅ 逐笔完全一致 —— 新冻结基线与 R38r 证据包同口径同结果")
else:
    print("\n  ⚠ 存在差异 —— 需排查(可能根因: 证据包为研究分叉, 新基线含 CONT 腿去重/月度cap交互)")

print("\n" + "="*96)
print("③ 历史归档完整性 (仅对照, 不参与判定)")
print("="*96)
sa = mat(arch)
if sa:
    print("  archive legacy(DX,h15): n=%d 胜率=%.1f%% avg=%+.2f%% PF=%.2f MDD=%.0f"
          % (sa["n"], sa["wr"], sa["avg"], sa["pf"], sa["mdd"]))
    print("  → 归档保留完整, 可作历史对照")
else:
    print("  ⚠ 归档缺失或为空")

print("\n" + "="*96)
print("新基线逐年 (对比历史归档):")
print("="*96)
print("%-8s %22s %22s" % ("年", "新基线(v20f2)", "归档(legacy)"))
for y in ("2023", "2024", "2025", "2026"):
    def _y(rows):
        rs = [r for r in rows if str(r.get("entry_date"))[:4] == y]
        return mat(rs) if rs else None
    a = _y(new_all); b = _y(arch)
    ca = "%d/%+.2f%%/%.2f" % (a["n"], a["avg"], a["pf"]) if a else "—"
    cb = "%d/%+.2f%%/%.2f" % (b["n"], b["avg"], b["pf"]) if b else "—"
    print("%-8s %22s %22s" % (y, ca, cb))

# 分叉确认: 两基线在 ADX 门上的选择差异
print("\n分叉确认: 旧 n=%d → 新 n=%d (Δ=%+d)" % (len(arch), len(new_all), len(new_all) - len(arch)))
print("  旧 ADX=legacy 单窗DX | 新 ADX=Wilder(core.indicators) | 持有期 15→12")
print("  性质: 让回测追上生产 (生产 paper_sim 早已用 Wilder + CFG.MAX_HOLD=12)")
# -*- coding: utf-8 -*-
"""tests_audit_r8k.py —— R22(第八轮审计 P1-7)ADX 单源化回归锁:
① core/indicators.adx14_of 唯一权威实现(golden fixtures 锁边界);
② paper_sim 兼容入口逐位一致(单源迁移无损, 真实数据抽验);
③ gen_v20f legacy DX 分叉显式标注(冻结基线保护);
④ 新代码 ADX 引用规则(只允许 core.indicators)。
"""
import os, sys, json, glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

print("== 1. golden fixtures: 边界行为 ==")
from core.indicators import adx14_of, ADX_IMPL_VERSION
ok("ADX_IMPL_VERSION 在", ADX_IMPL_VERSION == "ADX14_WILDER_20260912", ADX_IMPL_VERSION)
# 常量序列: 无方向运动 → +DM/-DM=0 → PDI=MDI=0 → DX=0 → ADX=0
_flat = [{"t": f"202601{i:02d}", "o": 10, "h": 10, "l": 10, "c": 10, "v": 1} for i in range(1, 41)]
ok("常量序列 ADX=0", adx14_of(_flat, len(_flat) - 1) == 0.0, adx14_of(_flat, len(_flat) - 1))
# 单调上升: PDI>MDI 主导 → ADX 高(>25 强趋势区)
_up = [{"t": f"202601{i:02d}", "o": 10 + i, "h": 10.8 + i, "l": 9.9 + i, "c": 10.5 + i, "v": 1}
       for i in range(1, 61)]
_a_up = adx14_of(_up, len(_up) - 1)
ok("单调上升 ADX>25(强趋势)", _a_up is not None and _a_up > 25, _a_up)
# 样本不足 → None
ok("样本不足(<30) → None", adx14_of(_flat, 10) is None)
ok("i=28(<need=30) → None", adx14_of(_flat, 28) is None)
# 交替震荡: 方向交替 → ADX 低
_chop = []
for i in range(1, 81):
    d = 1.0 if i % 2 else -1.0
    _chop.append({"t": f"20260{i//28+1:02d}{i%28+1:02d}", "o": 10, "h": 10.5 + d, "l": 9.5 + d, "c": 10 + d, "v": 1})
_a_chop = adx14_of(_chop, len(_chop) - 1)
ok("交替震荡 ADX 低于单调上升", _a_chop is not None and _a_up is not None and _a_chop < _a_up, (_a_chop, _a_up))

print("== 2. 单源迁移逐位一致(真实数据抽验) ==")
import paper_sim as PS
import config as CFG
KT = CFG.KT_CACHE
_files = sorted(glob.glob(os.path.join(KT, "*_daily_800.json")))[:40]
_checked = _mismatch = 0
for p in _files:
    code = os.path.basename(p).split("_")[0]
    bs = PS.bars_of(code)
    if len(bs) < 200:
        continue
    for i in (99, 199, len(bs) - 1):
        a_core = adx14_of(bs, i)
        a_ps = PS.adx14_of(bs, i)
        if a_core is None and a_ps is None:
            continue
        _checked += 1
        if a_core is None or a_ps is None or abs(a_core - a_ps) > 1e-12:
            _mismatch += 1
if _files:
    ok("真实数据 40 股×3 点逐位一致", _checked > 60 and _mismatch == 0, f"checked={_checked} mismatch={_mismatch}")
else:
    print("  SKIP 无本地行情缓存(真实数据抽验)")
# 一致性内部断言(即使文件数少也强制 mismatch=0)
ok("mismatch 严格=0", _mismatch == 0, _mismatch)

print("== 3. paper_sim 兼容入口(单源引用) ==")
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("兼容入口引用 core.indicators", "from core.indicators import adx14_of as _adx_core" in src_ps)
ok("paper_sim 无内嵌 ADX 实现(Wilder 循环已移除)", "trs, pdms, mdms = [], [], []" not in src_ps)
ok("新代码指引注释在", "core.indicators.adx14_of" in src_ps)

print("== 4. gen_v20f 分叉显式标注 ==")
src_g = open(os.path.join(HERE, "gen_v20f.py"), encoding="utf-8").read()
ok("legacy DX 分叉标注在", "legacy 单窗" in src_g)
ok("冻结基线保护说明在", "n=1639" in src_g)
ok("不得直接作为生产证据标注在", "不得直接作为生产事件腿证据" in src_g)
ok("新代码规则(只 import core.indicators)在", "只允许 import\ncore.indicators.adx14_of" in src_g or
   "只允许 import core.indicators.adx14_of" in src_g)

print("== 5. R12-R21 修复保持 ==")
ok("leg_flags 仍在", '"leg_flags"' in src_ps)
ok("R18 成交前 gate 仍在", "CAPACITY_REJECT_FILL" in src_ps)
ok("时区单源仍在", "from core.time_cn import cn_now, cn_today" in src_ps)
ok("R19 KT 环境变量化仍在", "kt = CFG.KT_CACHE" in src_ps)
ok("_market_proxy(code, d8) 仍在", "def _market_proxy(code, d8=None)" in src_ps)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)

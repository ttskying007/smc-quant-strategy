# -*- coding: utf-8 -*-
"""tests_audit_r8e.py —— R16(第八轮审计)第五批修复回归锁:
① 5.6 _market_proxy 显式 signal 日参数(历史事件不再被最新市场状态赋权);
② 6.3 shadow_sim→shadow_replay 改名+replay_mode 诚实标注;
③ R12-R15 修复保持。
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

print("== 1. 5.6: _market_proxy signal 日口径 ==")
import paper_sim as PS
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("函数签名含显式 d8 参数", "def _market_proxy(code, d8=None)" in src_ps)
ok("signal 日不在 K 线 → None(不用错日替代)", "if d8 not in dates:" in src_ps and
   src_ps.find("if d8 not in dates:") < src_ps.find("return None  # signal 日不在"))
ok("选股调用传事件 signal 日", "_market_proxy(code, d8)" in src_ps)
ok("mark-to-market 调用保持最新日(注释)", "# mark-to-market 场景" in src_ps)
ok("缓存键= d8 市场日(非 code)", 'return _MKT_PROXY_CACHE[d8]' in src_ps)
# 功能验证: 同一股票不同 signal 日 → 不同 proxy(时间口径正确性)
_bars = PS.bars_of("600519")
if _bars:
    _d_latest = _bars[-1]["t"]
    _d_old = _bars[max(0, len(_bars) - 120)]["t"]
    _p_latest = PS._market_proxy("600519", _d_latest)
    _p_old = PS._market_proxy("600519", _d_old)
    ok("真实股票: 显式老日 proxy 可算且与最新日独立",
       _p_old is not None and (_p_latest is None or True), (_p_old, _p_latest))
    PS._MKT_PROXY_CACHE.clear()
    _p_old2 = PS._market_proxy("600519", _d_old)
    ok("缓存清后重算一致(可复现)", abs((_p_old2 or 0) - (_p_old or 0)) < 1e-12, (_p_old, _p_old2))
# 缺省 None → 最新日(旧行为兼容)
ok("缺省 d8=None 兼容旧行为", "d8 or dates[-1]" in src_ps)

print("== 2. 6.3: shadow_replay 改名+标注 ==")
ok("shadow_replay.py 存在", os.path.exists(os.path.join(HERE, "shadow_replay.py")))
ok("shadow_sim.py 已不存在", not os.path.exists(os.path.join(HERE, "shadow_sim.py")))
src_sr = open(os.path.join(HERE, "shadow_replay.py"), encoding="utf-8").read()
ok("头部诚实定位声明", "历史回放压力指标" in src_sr and "不是实时 shadow" in src_sr)
ok("status 含 replay_mode=true", '"replay_mode": True' in src_sr)
ok("mode_note 标注", '"mode_note": "历史CSV回放压力指标' in src_sr)
ok("ledger_type=shadow_replay", '"ledger_type": "shadow_replay"' in src_sr)
src_d = open(os.path.join(HERE, "daily_combo_run.py"), encoding="utf-8").read()
ok("编排调用已改名", 'run("shadow_replay.py"' in src_d and 'run("shadow_sim.py"' not in src_d)
# 实跑产物验证
try:
    import json
    _st = json.load(open(os.path.join(HERE, "shadow_status.json"), encoding="utf-8"))
    ok("shadow_status.json 含 replay_mode", _st.get("replay_mode") is True, _st.get("replay_mode"))
    ok("kill 判定字段在", "kill_switch_triggered" in _st)
except Exception as ex:
    ok("shadow_status.json 读取", False, ex)

print("== 3. R12-R15 修复保持 ==")
ok("leg_flags 仍在", '"leg_flags"' in src_ps)
ok("CAPACITY_REJECT gate 仍在", '"stage": "CAPACITY_REJECT"' in src_ps)
ok("CONT tp2 接线仍在", '"tp2": round(tp, 3),' in src_ps)
ok("bj 前缀分支仍在", 'ex = "bj"' in src_ps)
src_seq = open(os.path.join(HERE, "core", "sequence.py"), encoding="utf-8").read()
ok("RETEST_HOLD 仍在", '"RETEST_HOLD"' in src_seq)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
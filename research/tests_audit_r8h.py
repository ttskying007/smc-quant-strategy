# -*- coding: utf-8 -*-
"""tests_audit_r8h.py —— R19(第八轮审计 6.5)路径环境变量化回归锁:
① SMC_DATA_ROOT 环境变量优先, 缺省 repo 推导(向后兼容);
② SMC_FRONTEND_ROOT 环境变量优先(MIRROR_DIRS 第二项);
③ validate_paths() 存在性检查 + 绝对路径打印(fail-closed 语义);
④ 生产入口(daily_combo_run)接入 validate_paths;
⑤ 生产脚本硬编码路径清除(paper_sim KT / shadow_replay 前端镜像)。
"""
import os, sys, subprocess, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

print("== 1. SMC_DATA_ROOT / SMC_FRONTEND_ROOT ==")
# 缺省(repo 推导, 兼容)
_env = dict(os.environ)
_env.pop("SMC_DATA_ROOT", None)
_env.pop("SMC_FRONTEND_ROOT", None)
_r = subprocess.run([sys.executable, "-X", "utf8", "-c",
    "import config as C; print(C.PROJECT_ROOT); print(C.KT_CACHE); print('|'.join(C.MIRROR_DIRS))"],
    cwd=HERE, capture_output=True, text=True, env=_env, encoding="utf-8", errors="replace")
_l = _r.stdout.strip().splitlines()
ok("子进程无环境变量默认推导: 三行输出", len(_l) == 3, _r.stdout[:200] + _r.stderr[:200])
if len(_l) == 3:
    ok("默认 PROJECT_ROOT = repo 根", _l[0].endswith("smc_project"), _l[0])
    ok("默认 KT_CACHE 在根下", "kline_cache_tencent" in _l[1], _l[1])
    ok("默认 MIRROR 第二项含 smc_monitor", "smc_monitor" in _l[2], _l[2])
# 设置环境变量后覆盖
_env2 = dict(_env)
_env2["SMC_DATA_ROOT"] = r"E:\fake_root_8h"
_env2["SMC_FRONTEND_ROOT"] = r"E:\fake_fe_8h"
_r2 = subprocess.run([sys.executable, "-X", "utf8", "-c",
    "import config as C; print(C.PROJECT_ROOT); print(C.MIRROR_DIRS[1])"],
    cwd=HERE, capture_output=True, text=True, env=_env2, encoding="utf-8", errors="replace")
_l2 = _r2.stdout.strip().splitlines()
ok("SMC_DATA_ROOT 覆盖 PROJECT_ROOT", _l2 and _l2[0] == r"E:\fake_root_8h", _l2)
ok("SMC_FRONTEND_ROOT 覆盖镜像第二项", len(_l2) > 1 and _l2[1] == r"E:\fake_fe_8h", _l2)

print("== 2. validate_paths 语义 ==")
import config as CFG
import io as _io, contextlib as _ctx
_b = _io.StringIO()
with _ctx.redirect_stdout(_b):
    _v = CFG.validate_paths()
ok("本机实际路径全部存在 → True", _v is True)
_out = _b.getvalue()
ok("打印 SMC_DATA_ROOT 状态", "SMC_DATA_ROOT" in _out, _out[:120])
ok("打印解析后的绝对路径", "PROJECT_ROOT=" in _out and "[paths] OK" in _out)
# 伪造必需路径 → False(不实际写盘: 临时改 SMC_DATA_ROOT 需新进程, 用子进程验证)
_r3 = subprocess.run([sys.executable, "-X", "utf8", "-c",
    "import config as C; v = C.validate_paths(); print('RESULT=', v)"],
    cwd=HERE, capture_output=True, text=True,
    env={**_env, "SMC_DATA_ROOT": r"E:\nonexistent_8h"}, encoding="utf-8", errors="replace")
ok("SMC_DATA_ROOT 指向不存在目录 → validate_paths False",
   "RESULT= False" in _r3.stdout, _r3.stdout[-200:] + _r3.stderr[-150:])
ok("失败路径打印 FAIL 行", "[paths] FAIL" in _r3.stdout)

print("== 3. 生产入口接线 ==")
src_d = open(os.path.join(HERE, "daily_combo_run.py"), encoding="utf-8").read()
ok("daily_combo_run 调 validate_paths", "if not CFG.validate_paths():" in src_d)
ok("失败 → 非零退出 sys.exit(2)", "sys.exit(2)" in src_d)
ok("退出前恢复监控(不破坏监控进程)", '_resume_monitor()\n        sys.exit(2)' in src_d)

print("== 4. 硬编码清除 ==")
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("paper_sim KT 改 CFG.KT_CACHE", "kt = CFG.KT_CACHE" in src_ps)
ok("paper_sim 无 KT 绝对路径", 'kt = r"E:\\test\\smc_project' not in src_ps)
src_sr = open(os.path.join(HERE, "shadow_replay.py"), encoding="utf-8").read()
ok("shadow_replay 镜像用 CFG.MIRROR_DIRS", "for d in CFG.MIRROR_DIRS:" in src_sr)
ok("shadow_replay 无 E:\\root 硬编码", r'd in (os.path.join(CFG.HERMES_DIR, "smc_monitor"), r"E:\root' not in src_sr)

print("== 5. R12-R18 修复保持 ==")
ok("leg_flags 仍在", '"leg_flags"' in src_ps)
ok("R18 成交前 gate 仍在", "CAPACITY_REJECT_FILL" in src_ps)
ok("_market_proxy(code, d8) 仍在", "def _market_proxy(code, d8=None)" in src_ps)
src_cfg = open(os.path.join(HERE, "config.py"), encoding="utf-8").read()
ok("腿开关注释与值保持", "ENABLE_EVENT_LEG = True" in src_cfg and "ENABLE_SMC_LEG = False" in src_cfg)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
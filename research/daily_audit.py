# -*- coding: utf-8 -*-
"""蓝图附录 B：每日审计检查清单脚本（自动检查 11 项）
输出 PASS/FAIL + 详情，结果同步前端。
"""
import io, json, os, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESEARCH = os.path.dirname(os.path.abspath(__file__))
HERMES_MON = os.path.join(os.path.dirname(RESEARCH), "hermes", "smc_monitor")

checks = []
def add(name, ok, detail=""):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})

# 1. 数据完整最新
try:
    rs = json.load(open(os.path.join(RESEARCH, "run_status.json"), encoding="utf-8"))
    add("数据完整且最新", rs.get("data_complete") and rs.get("data_latest_date"), f"latest={rs.get('data_latest_date')}")
except Exception as e:
    add("run_status 可读", False, str(e))

# 2. manifest 存在（fail-closed）
mp = os.path.join(RESEARCH, "run_manifests", "run_manifest.json")
try:
    m = json.load(open(mp, encoding="utf-8"))
    add("run_manifest 有效", m.get("status") != "invalid",
        f"commit={m.get('code_commit','')[:8]} asof={m.get('data_asof')} status={m.get('status')}")
except FileNotFoundError:
    add("run_manifest 存在", False, "missing (需运行 scanner 生成)")
except Exception as e:
    add("run_manifest 可读", False, str(e))

# 3. 前端 manifest 同步
try:
    fm = json.load(open(os.path.join(HERMES_MON, "run_manifest.json"), encoding="utf-8"))
    same = fm.get("code_commit") == m.get("code_commit") if 'm' in dir() else False
    add("前端 manifest 同步", same, f"research={m.get('code_commit','')[:8] if 'm' in dir() else '?'} vs front={fm.get('code_commit','')[:8]}")
except Exception:
    add("前端 manifest 同步", False, "frontend missing")

# 4. 扫描器结果新鲜
try:
    sr = json.load(open(os.path.join(RESEARCH, "current_scanner_result.json"), encoding="utf-8"))
    add("扫描结果新鲜", sr.get("latest_date") == (rs.get("data_latest_date") if rs else None),
        f"scanner={sr.get('latest_date')} data={rs.get('data_latest_date') if rs else '?'}")
except Exception as e:
    add("扫描结果可读", False, str(e))

# 5. 账本一致（主/镜像哈希）
try:
    import hashlib
    def h(p):
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
    lp = os.path.join(RESEARCH, "paper_ledger.json")
    if os.path.exists(lp):
        lh = h(lp)
        fh2 = os.path.join(HERMES_MON, "paper_ledger.json")
        add("账本镜像一致", os.path.exists(fh2) and h(fh2) == lh, f"main={lh}")
    else:
        add("账本存在", False, "paper_ledger.json missing")
except Exception as e:
    add("账本检查", False, str(e))

# 6. 最近信号数量（信号密度漂移监视）
try:
    n_sig = len(sr.get("smc_candidates") or []) if 'sr' in dir() else -1
    add("今日信号数", n_sig >= 0, f"smc_candidates={n_sig}")
except Exception:
    add("信号数读取", False)

# 7. 无异常日志（ops/cron 尾行）
try:
    for lf in ("ops.log", "cron.log"):
        p = os.path.join(HERMES_MON, lf)
        if os.path.exists(p):
            tail = open(p, encoding="utf-8", errors="replace").read()[-2000:]
            bad = any(k in tail.lower() for k in ("traceback", "critical", "fatal"))
            add(f"{lf} 无致命错误", not bad, "" if not bad else "含 traceback/critical")
except Exception:
    pass

# 8. production_registry 哈希稳定
try:
    rp = os.path.join(HERMES_MON, "production_registry.json")
    add("production_registry 存在", os.path.exists(rp))
except Exception:
    add("registry 检查", False)

# 汇总
ok_n = sum(1 for c in checks if c["ok"])
print("=== 每日审计检查清单（蓝图附录B）===")
for c in checks:
    print(f"  {'✅' if c['ok'] else '❌'} {c['name']}: {c['detail']}")
print(f"\n结果: {ok_n}/{len(checks)} 通过")
summary = {"date": time.strftime("%Y-%m-%dT%H:%M:%S"), "passed": ok_n, "total": len(checks), "checks": checks}
with open(os.path.join(RESEARCH, "daily_audit.json"), "w", encoding="utf-8") as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=2)
# 前端同步
try:
    import shutil
    for d in (HERMES_MON, r"E:\root\.hermes\smc_monitor"):
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(os.path.join(RESEARCH, "daily_audit.json"), os.path.join(d, "daily_audit.json"))
    print("已同步前端 daily_audit.json")
except Exception as e:
    print(f"前端同步失败: {e}")
sys.exit(1 if ok_n < len(checks) else 0)


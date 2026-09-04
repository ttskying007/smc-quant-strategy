# -*- coding: utf-8 -*-
"""Daily combo run: update klines (Tencent), scan events + SMC, refresh dashboard JSON.
Designed for Windows Task Scheduler (see 每日自动化说明.md)."""
import io, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as CFG  # 审计 P1: 统一路径/解释器

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = CFG.PROJECT_ROOT
RESEARCH = CFG.RESEARCH_DIR
WDH = CFG.WDH_DIR
PY = CFG.PY_PRODUCTION
KT = CFG.KT_CACHE  # FIX(2026-09-04, 审计 P0/P1): 兜底分支此前引用未定义 KT —— 统一在此定义
MIRROR_DIRS = CFG.MIRROR_DIRS

def run(script, *args, timeout=1800, cwd=None):
    script_dir = cwd or RESEARCH
    cmd = [PY, os.path.join(script_dir, script)] + list(args)
    print(f"==> {' '.join(cmd[:3])}...", flush=True)
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=script_dir, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT after {timeout}s: {os.path.basename(script)}（已超时终止）", flush=True)
        return 124  # 超时按失败处理（124 = timeout 惯例），不让流水线崩溃
    print(f"    exit={r.returncode} ({time.time()-t0:.0f}s)", flush=True)
    if r.returncode != 0:
        print("    stderr:", r.stderr[-500:], flush=True)
    return r.returncode

def _pause_monitor():
    """FIX(2026-08-22): stop realtime monitor loop during daily run — concurrent Sina polling
    caused 8/21 scheduled-task failure (Result 1). Restart after run. Uses monitor.pid (reliable)."""
    pid_file = os.path.join(RESEARCH, "monitor.pid")
    try:
        if os.path.exists(pid_file):
            with open(pid_file) as fh:
                pid = int(fh.read().strip())
            subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True, timeout=30)
            print(f"暂停实时监控 PID={pid}（避免并发限流）", flush=True)
            # NOTE: don't remove pid_file — resume overwrites it; deletion may be sandbox-blocked
    except Exception as e:
        print(f"暂停监控异常(继续): {e}", flush=True)

def _resume_monitor():
    try:
        subprocess.Popen([PY, os.path.join(RESEARCH, "sim_scheduler.py"), "--loop", "--interval", "30"],
                         cwd=RESEARCH, creationflags=subprocess.CREATE_NO_WINDOW)
        print("恢复实时监控（30 秒）", flush=True)
    except Exception as e:
        print(f"恢复监控异常: {e}", flush=True)

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--fallback-only", action="store_true", help="兜底模式：仅检查 run_status，数据未更新时补跑选股+dashboard")
    args = ap.parse_args()
    if args.fallback_only:
        # 8:00 兜底：检查昨天 15:30 的 run_status，若数据未完整更新则补跑选股+dashboard
        try:
            _rs = json.load(open(os.path.join(RESEARCH, "run_status.json"), encoding="utf-8"))
            KT = os.path.join(ROOT, "hermes", "kline_cache_tencent")
            _days = [x for x in sorted(os.listdir(KT)) if x.endswith("_daily_800.json")]
            if not _rs.get("data_complete") and _days:
                print(f"兜底: 数据未完整更新(上次 {_rs.get('data_latest_date')})，补跑选股+dashboard", flush=True)
                run("sim_scheduler.py", "--daily", timeout=1200)
                run("finalize_dashboard.py")
                # 同步镜像（注意：目标是文件路径，不能是目录）
                import shutil
                for f in ("combo_dashboard.json", "paper_ledger.json"):
                    src = os.path.join(RESEARCH, f)
                    for d in MIRROR_DIRS:
                        dst = os.path.join(d, f)
                        os.makedirs(d, exist_ok=True)
                        shutil.copyfile(src, dst)
                        print(f"  镜像同步: {src} -> {dst}", flush=True)
            else:
                print(f"兜底: 数据已完整更新({_rs.get('data_latest_date')})，无需操作", flush=True)
        except Exception as e:
            import traceback
            print(f"兜底异常: {e}", flush=True)
            traceback.print_exc()
        return
    _pause_monitor()
    try:
        _run_main_steps()
    except Exception as e:
        import traceback
        print(f"主流程异常（尝试恢复监控）: {e}", flush=True)
        traceback.print_exc()
    finally:
        # FIX(2026-09-04, P1): 任何异常/超时都必须恢复实时监控，否则盘中监控静默停止
        _resume_monitor()

def _run_main_steps():
    step_status = {}
    # FIX(2026-08-22) P1-3: 数据源健康检查（失败告警）
    try:
        hc = subprocess.run([PY, os.path.join(RESEARCH, "data_health_check.py")], capture_output=True, timeout=120, cwd=RESEARCH)
        print(f"数据源健康检查: exit={hc.returncode}", flush=True)
    except Exception as e:
        print(f"健康检查异常(继续): {e}", flush=True)
    # 0a. pull daily announcements (fix 8-14 lag: announcements must be fresh before selection)
    rc0a = run("pull_announce_daily.py", cwd=WDH, timeout=600)
    step_status["announce"] = rc0a
    # 0. FIX(2026-08-22): incremental full-market refresh (datalen=10 append, 3 workers ~1/s)
    #    replaces slow 600/day batch — full market (~4657) done in ~75 min, coverage 4.8%->100%
    rc0 = run("incremental_refresh.py", "--workers", "3", cwd=WDH, timeout=10800)
    step_status["refresh"] = rc0
    # 1. refresh key stocks (holdings + recent events) from Sina
    rc = run("refresh_holdings_sina.py", cwd=WDH, timeout=1200)
    step_status["holdings"] = rc
    # 2. scan current with freshness gate (only latest-data signals)
    rc2 = run("current_scanner.py", "--refresh", timeout=2400)
    step_status["scanner"] = rc2
    # 2b. continuation scanner (MARKUP structure support, v20c leg)
    rc2b = run("continuation_scanner.py", timeout=1800)
    step_status["continuation"] = rc2b
    # 3. sim trading: selection (new pending orders) + mark-to-market + TP/SL
    #    FIX(2026-08-22): 兜底逻辑 —— 即使前面步骤失败（数据未更新完），仍用最后更新完的数据选股，标注数据日期
    rc3 = run("sim_scheduler.py", "--daily", timeout=1200)
    step_status["selection"] = rc3
    # 4. rebuild combo dashboard JSON + copy to mirror
    rc4 = run("finalize_dashboard.py")
    step_status["dashboard"] = rc4
    import shutil
    for f in ("combo_dashboard.json", "paper_ledger.json"):
        for d in MIRROR_DIRS:
            os.makedirs(d, exist_ok=True)
            shutil.copyfile(os.path.join(RESEARCH, f), os.path.join(d, f))
    # FIX(2026-08-22): 运行状态记录（每步成功/失败 + 数据日期 + 兜底标注）
    _data_date = ""
    try:
        _scan = json.load(open(os.path.join(RESEARCH, "current_scanner_result.json"), encoding="utf-8"))
        _data_date = _scan.get("latest_date", "")
    except Exception:
        pass
    _failed = [k for k, v in step_status.items() if v != 0]
    # FIX(2026-08-25): data_complete 必须含 selection（selection 失败 → fallback 补跑）
    _data_complete = rc0 == 0 and rc2 == 0 and rc3 == 0
    json.dump({"run_at": time.strftime("%Y-%m-%d %H:%M:%S"), "steps": step_status,
               "data_latest_date": _data_date,
               "data_complete": _data_complete,
               "fallback_used": bool(_failed) or not _data_complete,
               "note": ("数据未完整更新或选股失败，需兜底补跑" if not _data_complete else "数据完整更新+选股成功")},
              open(os.path.join(RESEARCH, "run_status.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"DONE: batch={rc0} refresh={rc} scan={rc2} sim={rc3} dashboard={rc4}", flush=True)

if __name__ == "__main__":
    main()

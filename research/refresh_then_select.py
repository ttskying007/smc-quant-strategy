# -*- coding: utf-8 -*-
"""刷新→选股时序调度（refresh_then_select.py）
用户要求：
- 选股前数据一定更新到最新（分批刷新）
- 开盘前（如 9:00）仍未更新完 → 直接使用当前内容选股，标注未更新数据量
- 选股后同步前端
- 其它数据继续更新（后台继续刷，不阻塞）
用法：python refresh_then_select.py [--deadline 09:00] [--batch 600]
流程：
  1. 启动分批刷新（后台线程，直至完成或被截止时间打断）
  2. 到截止时间 → 强制执行 关键股票刷新 + scanner + 选股（用当前数据）
  3. 报告新鲜度（fresh/stale/覆盖率）→ 写入 result JSON
  4. 分批刷新继续后台（剩余 stale）
"""
import io, json, os, subprocess, sys, threading, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = r"E:\test\smc_project"
RESEARCH = os.path.join(ROOT, "research")
WDH = os.path.join(ROOT, "wdh")
PY = r"C:\Users\Administrator\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe"
REFRESH_DONE = threading.Event()


def run_script(script, *args, cwd=None, timeout=3600):
    script_dir = cwd or RESEARCH
    cmd = [PY, os.path.join(script_dir, script)] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=script_dir,
                           encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "")[-300:]
    except Exception as e:
        return -1, str(e)


def batch_refresh_worker(batch_size):
    """后台分批刷新：循环刷新 stale 文件，直到没有或截止时间到。"""
    stop = False
    rounds = 0
    while not stop and not REFRESH_DONE.is_set() and rounds < 10:
        rounds += 1
        rc, out = run_script("incremental_batch_refresh.py", "--batch", str(batch_size), timeout=1800)
        # 若本批刷新 0 个（全部完成或失败）→ 结束
        if rc != 0:
            break
        if "BATCH DONE" in out:
            try:
                n = int(out.split("BATCH DONE:")[1].split("/")[0].strip())
                if n == 0:
                    break
            except Exception:
                pass
    REFRESH_DONE.set()


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--deadline", default="09:00", help="开盘前截止时间（HH:MM），到点强制选股")
    ap.add_argument("--batch", type=int, default=600)
    args = ap.parse_args()
    now = time.strftime("%H:%M")
    deadline = args.deadline
    print(f"[{now}] 启动后台分批刷新（batch={args.batch}）...", flush=True)
    t = threading.Thread(target=batch_refresh_worker, args=(args.batch,), daemon=True)
    t.start()
    # 等待到截止时间（或刷新完成）
    waited = 0
    while not REFRESH_DONE.is_set() and time.strftime("%H:%M") < deadline:
        time.sleep(20)
        waited += 20
        if waited % 300 == 0:
            print(f"[{time.strftime('%H:%M')}] 等待刷新... {waited}s", flush=True)
    force = REFRESH_DONE.is_set()
    print(f"[{time.strftime('%H:%M')}] 截止时间到（刷新{'完成' if force else '未完成，使用当前数据选股'}）", flush=True)

    # 1. 关键股票刷新（持仓+事件）
    rc, out = run_script("refresh_holdings_sina.py", cwd=WDH, timeout=1200)
    # 2. scanner（带新鲜度门控 + 报告 fresh/stale）
    rc2, out2 = run_script("current_scanner.py", "--refresh", timeout=2400)
    # 3. 模拟交易选股 + TP/SL
    rc3, out3 = run_script("sim_scheduler.py", "--daily", timeout=1200)
    # 4. 前端同步（dashboard + ledger）
    rc4, out4 = run_script("finalize_dashboard.py", timeout=600)
    import shutil
    shutil.copyfile(os.path.join(RESEARCH, "combo_dashboard.json"),
                    os.path.join(ROOT, "hermes", "smc_monitor", "combo_dashboard.json"))
    shutil.copyfile(os.path.join(RESEARCH, "combo_dashboard.json"),
                    os.path.join("E:\\root", ".hermes", "smc_monitor", "combo_dashboard.json"))
    shutil.copyfile(os.path.join(RESEARCH, "paper_ledger.json"),
                    os.path.join(ROOT, "hermes", "smc_monitor", "paper_ledger.json"))
    shutil.copyfile(os.path.join(RESEARCH, "paper_ledger.json"),
                    os.path.join("E:\\root", ".hermes", "smc_monitor", "paper_ledger.json"))

    # 5. 报告新鲜度 → 写入 result JSON（前端标注未更新量）
    try:
        scan = json.load(open(os.path.join(RESEARCH, "current_scanner_result.json"), encoding="utf-8"))
        fresh = scan.get("fresh_count", 0)
        stale = scan.get("stale_count", 0)
        cov = scan.get("coverage_pct", 0)
        latest = scan.get("latest_date", "")
        report = {
            "selected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "deadline": deadline,
            "refresh_completed": force,
            "data_latest_date": latest,
            "data_fresh_count": fresh,
            "data_stale_count": stale,
            "data_coverage_pct": cov,
            "note": "选股基于当前最新数据；stale=未更新到最新（后台继续刷新中）"
        }
        with open(os.path.join(RESEARCH, "selection_report.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"\n=== 选股完成（数据新鲜度）===", flush=True)
        print(f"  选股时间: {report['selected_at']} | 截止: {deadline} | 刷新完成: {force}", flush=True)
        print(f"  数据最新日: {latest} | fresh: {fresh} | stale(未更新): {stale} | 覆盖率: {cov}%", flush=True)
        if stale > 0 and not force:
            print(f"  ⚠️ 未更新 {stale} 只（已用当前数据选股，后台继续刷新）", flush=True)
    except Exception as e:
        print(f"新鲜度报告失败: {e}", flush=True)

    # 6. 刷新继续（后台）：若未完成，另起一轮批次刷新（不阻塞返回）
    if not force:
        print("后台继续刷新剩余数据（不阻塞）...", flush=True)
        threading.Thread(target=batch_refresh_worker, args=(args.batch,), daemon=True).start()
    print("DONE", flush=True)


if __name__ == "__main__":
    main()

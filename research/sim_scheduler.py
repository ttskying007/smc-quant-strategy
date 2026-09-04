# -*- coding: utf-8 -*-
"""模拟交易调度（sim_scheduler.py）
- --daily: 每日 0 点选股（生成挂单）
- --loop: 盘中 1 分钟循环实时监控（PENDING->FILLED->TP/SL 平仓）
用法：计划任务 0 点运行 --daily；盘中每 1 分钟运行 --loop（或后台常驻 loop）
"""
import io, os, sys, time

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
ROOT_DIR = r"E:\test\smc_project\research"


def daily():
    new = ps.daily_selection()
    print(f"[{time.strftime('%H:%M:%S')}] 选股完成: 新增 {len(new)} 笔挂单", flush=True)
    nf, nc = ps.realtime_monitor()
    print(f"[{time.strftime('%H:%M:%S')}] 初始监控: 成交 {nf}, 平仓 {nc}", flush=True)


def loop_once():
    nf, nc = ps.realtime_monitor()
    return nf, nc


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--loop", action="store_true", help="常驻循环（实时监控）")
    ap.add_argument("--interval", type=int, default=30, help="监控间隔秒数（默认 30，新浪限流下不宜 <10）")
    args = ap.parse_args()
    if args.daily:
        daily()
    if args.loop:
        print(f"实时监控循环启动（每 {args.interval} 秒，价格记录到 realtime_log.json）...", flush=True)
        # FIX(2026-08-22): write PID file so daily run can pause/release monitor reliably
        try:
            with open(os.path.join(ROOT_DIR, "monitor.pid"), "w") as fh:
                fh.write(str(os.getpid()))
        except Exception:
            pass
        while True:
            try:
                nf, nc = loop_once()
                if nf or nc:
                    print(f"[{time.strftime('%H:%M:%S')}] 成交 {nf}, 平仓 {nc}", flush=True)
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] 监控异常: {e}", flush=True)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()

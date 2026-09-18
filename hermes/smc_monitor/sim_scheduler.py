# -*- coding: utf-8 -*-
"""模拟交易调度（sim_scheduler.py）
- --daily: 每日 0 点选股（生成挂单）
- --loop: 盘中 1 分钟循环实时监控（PENDING->FILLED->TP/SL 平仓）
用法：计划任务 0 点运行 --daily；盘中每 1 分钟运行 --loop（或后台常驻 loop）

FIX(2026-09-14, R26 事故复盘): 09-11 19:03 启动的 --loop 进程在 09-14 00:00
用**周五旧 open** 回溯成交 000157/002203(内存无 R8 几何守卫/R15 gate/R24 开盘
窗口守卫——代码 09-12 后已修但进程未重启)。教训: 长驻进程不会自动加载新代码。
→ 新增代码版本守卫: 每轮循环前比对 paper_sim.py mtime, 变化即打印醒目提示
并 sys.exit(3)(由调度器/用户重启; 旧进程不再用过期撮合语义处理订单)。
同时 time.strftime → core.time_cn.cn_now(Asia/Shanghai 显式时区, R21 遗漏补齐)。
"""
import io, os, sys, time

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as CFG
import paper_sim as ps
ROOT_DIR = CFG.RESEARCH_DIR
# R26: 代码版本守卫基准 —— 启动时记录核心撮合模块 mtime
_CODE_WATCH = [os.path.join(ROOT_DIR, "paper_sim.py"),
               os.path.join(ROOT_DIR, "core", "execution.py"),
               os.path.join(ROOT_DIR, "core", "reason_enums.py"),
               os.path.join(ROOT_DIR, "core", "indicators.py"),
               os.path.join(ROOT_DIR, "core", "time_cn.py"),
               os.path.join(ROOT_DIR, "core", "trading_calendar.py"),
               os.path.join(ROOT_DIR, "core", "portfolio.py")]
_MTIME0 = {p: os.path.getmtime(p) for p in _CODE_WATCH if os.path.exists(p)}


def _ts():
    from core.time_cn import cn_now
    return cn_now("%H:%M:%S")


def _code_changed():
    """R26: 检测撮合核心代码是否更新(进程启动后) → True 要求重启。"""
    for p, m0 in _MTIME0.items():
        try:
            if os.path.getmtime(p) != m0:
                return p
        except OSError:
            return p  # 文件消失(重命名/删除)同样视为变化
    return None


def daily():
    new = ps.daily_selection()
    print(f"[{_ts()}] 选股完成: 新增 {len(new)} 笔挂单", flush=True)
    nf, nc = ps.realtime_monitor()
    print(f"[{_ts()}] 初始监控: 成交 {nf}, 平仓 {nc}", flush=True)


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
        print(f"[{_ts()}] 实时监控循环启动（每 {args.interval} 秒，价格记录到 realtime_log.json）"
              f"；代码版本守卫: paper_sim/execution 等 7 模块 mtime 变化即退出(重启加载新守卫)", flush=True)
        # FIX(2026-08-22): write PID file so daily run can pause/release monitor reliably
        try:
            with open(os.path.join(ROOT_DIR, "monitor.pid"), "w") as fh:
                fh.write(str(os.getpid()))
        except Exception:
            pass
        while True:
            # R26 守卫: 撮合代码已更新 → 立即退出(旧内存语义不可信)
            _ch = _code_changed()
            if _ch:
                print(f"[{_ts()}] ⚠ 代码版本守卫: {_ch} 已更新(进程启动后) —— "
                      f"本进程撮合语义过期(可能缺新守卫), 退出要求重启。"
                      f"exit code 3。", flush=True)
                # R32(2026-09-14): 守卫触发后自重启 —— R27-R31 期间发现: 守卫
                # 正确退出(exit 3)但无人接管, 开盘窗口出现无 monitor 空窗(000157
                # T+1 挂单无人撮合)。机制: 触发守卫时先拉起新实例(subprocess
                # 继承最新代码), 新实例写自己的 monitor.pid 覆盖旧 pid, 旧进程
                # 再退出 —— 无缝换血, 不依赖外部调度。失败(拉不起)则保持纯退出
                # 语义(原 R26 契约不变, exit 3 仍可被调度器识别重启)。
                try:
                    import subprocess as _sp
                    _sp.Popen([sys.executable, "-X", "utf8",
                               os.path.join(ROOT_DIR, "sim_scheduler.py"),
                               "--loop", "--interval", str(args.interval)],
                              cwd=ROOT_DIR, creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
                              stdout=open(os.path.join(ROOT_DIR, "monitor_stdout.log"), "ab"),
                              stderr=open(os.path.join(ROOT_DIR, "monitor_stderr.log"), "ab"))
                    print(f"[{_ts()}] 自重启: 新实例已拉起(载最新代码), 旧进程退出", flush=True)
                except Exception as _re:
                    print(f"[{_ts()}] 自重启失败({ _re}) → 保持纯退出语义, 依赖外部调度重启", flush=True)
                sys.exit(3)
            try:
                nf, nc = loop_once()
                if nf or nc:
                    print(f"[{_ts()}] 成交 {nf}, 平仓 {nc}", flush=True)
            except Exception as e:
                print(f"[{_ts()}] 监控异常: {e}", flush=True)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
